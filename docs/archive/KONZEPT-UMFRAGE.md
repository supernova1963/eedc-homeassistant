# EEDC Community-Umfrage — Konzept

> **ARCHIVIERT (2026-08-13, Entscheid Gernot): kein akuter Bedarf mehr.** Nicht weil die Umfrage
> ausgefallen wäre, sondern weil ihre Fragen von der Entwicklung überholt wurden — zwischen dem
> Konzept (Mai) und heute liegen v3.29 bis v4.0.14.
>
> ⚠ **Der Trigger ist eingetreten, und niemand hat ihn geprüft.** Das Dokument verlangte „aktuelle
> Anzahl geteilter Anlagen abrufen, bei ≥ 30 Forum-Post planen" und nannte den Check ausdrücklich
> jederzeit möglich. **Am 2026-08-13 gemessen: 100 geteilte Anlagen in 16 Regionen**
> (`/api/statistics/global`) — die reduzierte Schwelle ist um mehr als das Dreifache überschritten,
> die *ursprüngliche* Schwelle von 100 exakt erreicht. Ein Trigger, den niemand abfragt, ist kein
> Trigger; er ist ein Vergessen mit Datum ([[feedback_trigger_als_ereignis_nicht_plan]]).
>
> ⛔ **Der fertige Umfragetext unten ist die eigentliche Begründung fürs Archiv — er fragt nach
> Gebautem.** Block C wollte wissen, ob sich jemand *„Energie-Tagesdetail — stündliche
> Aufschlüsselung einzelner Tage"*, *„Berechnungen zurück nach HA"* und *„… via MQTT"* wünscht:
> alle drei sind seither ausgeliefert. Block D fragte *„Speichererweiterung — lohnt sich mehr kWh
> für mein Profil?"* — das ist **#358 Phase 3**, seit **v4.0.14** im Komponenten-Hub, mit genau
> der versprochenen Begründung („konkrete Zahlen statt Faustformeln", simuliert auf den eigenen
> gemessenen Stunden). Eine Umfrage, die nach vorhandenen Funktionen fragt, misst nicht den Bedarf,
> sondern die Bekanntheit — das wäre eine andere Umfrage mit anderen Fragen.
>
> **Was NICHT mit archiviert wird — die vier Restposten und wo sie jetzt leben:**
>
> | Restposten | Heimat |
> | --- | --- |
> | „Meine Anlage öffentlich teilen" (Widget-Seite, Virality) | `memory/project_my_eedc_schublade.md` + **#110** („My eedc"-Widget-Dashboard, ab 3 Anfragen) — unverändert geparkt |
> | Community-Attraktivität & Reichweite (Share, SEO, Schnellvergleich) | `memory/project_community_attraktivitaet.md` + **#110** — unverändert geparkt |
> | **Gruppen-Vergleich (2–5 Nutzer)** · **Akkudoktor-Tools-Link** | ⚠ **hatten hier ihre einzige Heimat** — beide gehören zur Community-Site und sind bei der Attraktivitäts-Datei einzuordnen |
> | **MQTT Auto-Discovery (inbound)** — fremde Geräte-Topics erkennen statt eintragen | ⚠ **heimatlos und nicht gebaut.** Am Code geprüft: `mqtt_client.py` macht ausschließlich **Outbound**-Discovery (eedc meldet seine eigenen Sensoren bei HA an); eine Topic-**Erkennung** existiert nicht (kein Treffer im Backend) |
>
> **Investment-Assistent** (Block D) ist kein Restposten mehr, sondern zur Hälfte gebaut: Speicher
> über #358 Phase 2+3, dynamischer Tarif über die Preis-Sensoren. Offen bleiben PV-Erweiterung,
> Wärmepumpe und E-Auto/Wallbox als „lohnt sich das für mein Profil?"-Frage — sie hätten, wenn sie
> jemand will, ihre Heimat im Wirtschaftlichkeits-Konzept, nicht hier.
>
> Alles unterhalb ist der Stand vom 2026-05-09 und wird nicht mehr fortgeschrieben.

## Status (2026-05-09)

**Zurückgestellt** bis > 30 geteilte Anlagen erreicht sind.

- Letzter dokumentierter Stand (2026-04-04): 19 geteilte Anlagen, ~59 unique Clones/Tag
- Ursprüngliche Schwelle war 100 — auf 30 reduziert, da Early-Adopter-Feedback repräsentativ genug ist
- **Nächster Schritt vor Aktivierung:** aktuelle Anzahl geteilter Anlagen abrufen (Community-Server), bei ≥ 30 Forum-Post planen. Trigger-Check kann jederzeit erfolgen, blockiert nichts in der laufenden Roadmap.

## Plattform

- community.simon42.com **und** community-smarthome.com gleichzeitig (beide Discourse → nativer Poll)
- Zusätzlich GitHub Discussion möglich
- Freitext-Antworten (Block E) als Antworten auf den Forum-Post

## Einschätzung

**Stärken:**
- Block A (Wofür nutzt du EEDC?) ist selten so klar zu erheben
- Block D (Investment-Assistent) ist stärkste Differenzierung gegenüber Akkudoktor & Co.
- "Meine Anlage teilen mit Widgets" ist stärkste neue Idee: Virality + Showcase + Basis für Gruppen-Vergleich

**Hinweis zum Timing:**
- Nicht direkt nach Monatsabschluss starten (März/April) — dann kommen Bugs/Rückfragen
- Als "Stimmungstest von Early Adopters" kommunizieren, nicht als repräsentative Studie

---

## Fertiger Umfragetext

**Einleitung:**
> Wir möchten wissen, was euch wirklich wichtig ist. Die Ergebnisse fließen direkt in unsere Roadmap ein. Danke fürs Mitmachen!

**Block A — Wofür nutzt du EEDC hauptsächlich?** (Mehrfachauswahl)
- Live-Dashboard — Echtzeit-Überblick was gerade passiert
- Tages-/Monatsauswertung — wie war gestern / letzter Monat?
- Finanzanalyse — Kosten, Einsparungen, Wirtschaftlichkeit
- Prognosen & Aussichten — was kommt heute / morgen?
- Protokolle & Fehlersuche — was lief schief?
- Infothek — Verträge und Dokumente ablegen

**Block B — Wie nutzt du EEDC?**
- Variante: HA Add-on / Standalone Docker / Beides
- Häufigkeit: Mehrmals täglich / Einmal täglich / Nur gelegentlich

**Block C — Welche neuen Funktionen wünschst du dir?** (Mehrfachauswahl)
- Energie-Tagesdetail — stündliche Aufschlüsselung einzelner Tage + Wochenvergleich
- MQTT Auto-Discovery — Geräte-Topics automatisch erkennen statt manuell eintragen
- Gruppen-Vergleich — mit 2–5 anderen Nutzern die eigene Anlage vergleichen
- Berechnungen zurück nach HA — EEDC-Werte als HA-Sensoren
- Berechnungen zurück via MQTT — EEDC-Werte für eigene Automationen / Drittsysteme
- Meine Anlage öffentlich teilen — personalisierte Seite mit selbst gewählten Widgets (teilbar per Link)

**Block D — Investment-Assistent** (Mehrfachauswahl)
> EEDC kennt deine echten Verbrauchsdaten. Stell dir vor, es sagt dir auf Basis deines persönlichen Profils ob sich eine Investition lohnt — mit konkreten Zahlen statt Faustformeln. Was wäre für dich interessant?
- Speichererweiterung — lohnt sich mehr kWh für mein Profil?
- PV-Erweiterung — wie viel mehr Ertrag brächten zusätzliche Module?
- Wärmepumpe — rechnet sich das bei meinem Verbrauch?
- E-Auto + Wallbox — wie viel Überschuss könnte ich selbst nutzen?
- Dynamischer Tarif — würde sich Tibber / aWATTar bei mir lohnen?
- Persönliche Saisonprognose — was erwartet mich diesen Winter?

**Block E — Freitext**
> Was fehlt dir in EEDC am meisten? Was nervt dich? Was liebst du? Schreib es als Antwort auf diesen Post.

---

## Roadmap-Kandidaten aus der Konzeptphase

- **"Meine Anlage teilen"** — öffentlich per Link, konfigurierbare Widgets, Subdomain via ipv64, Virality-Potential, Basis für Gruppen-Vergleich
- **Investment-Assistent** — auf Basis echter Messdaten, Differenzierung gegenüber Akkudoktor PV-Tool
- **Gruppen-Vergleich** (2–5 Nutzer) — mittlerer bis hoher Aufwand, nur bei starker Nachfrage
- **Akkudoktor-Tools-Link** auf eedc-community für Neueinsteiger
