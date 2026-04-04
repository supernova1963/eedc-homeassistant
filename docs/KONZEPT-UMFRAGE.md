# EEDC Community-Umfrage — Konzept

## Status

**Zurückgestellt** bis > 30 geteilte Anlagen erreicht sind.

- Aktuell (2026-04-04): 19 geteilte Anlagen, ~59 unique Clones/Tag
- Ursprüngliche Schwelle war 100 — auf 30 reduziert, da Early-Adopter-Feedback repräsentativ genug ist

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
