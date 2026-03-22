# EEDC Demo-Video — Produktionsplan

**Ziel:** 2:30 Min YouTube-Video, Deutsch, Dark Mode, 1080p
**Version:** v3.1

---

## 1. Vorbereitung (vor dem Drehtag)

### Software installieren

| Tool | Zweck | Link |
|------|-------|------|
| **OBS Studio** | Screen-Recording | obsproject.com |
| **DaVinci Resolve** (Free) | Schnitt, Titel, Übergänge | blackmagicdesign.com |
| **Audacity** (optional) | Voiceover aufnehmen/schneiden | audacityteam.org |

### EEDC vorbereiten

- **EEDC auf v3.1.8** (aktuell) — prüfen, dass alles läuft
- **Testdaten:** Mindestens 2-3 Monate Monatsdaten, damit Auswertungen und Vorjahresvergleich gefüllt sind
- **Community-Anbindung** aktiv (für die Benchmark-Szene)
- **Sensor-Zuordnung** vollständig — alle Live-Sensoren konfiguriert (PV, Batterie, Netz, Wallbox falls vorhanden)
- **Dark Mode** aktivieren — sieht im Video professioneller aus

### Browser vorbereiten

- **Chrome/Firefox** — ein sauberes Profil oder Inkognito ohne Extensions
- **Bookmarks-Leiste ausblenden** (Ctrl+Shift+B in Chrome)
- **Tabs:** Nur ein Tab mit EEDC offen
- **Zoom:** 100% (Ctrl+0)
- **Fenster:** Fullscreen (F11)
- **Auflösung:** Monitor auf 1920×1080 setzen (OBS nimmt dann nativ 1080p auf)

### OBS einrichten

- **Source:** Display Capture (ganzer Bildschirm) oder Window Capture (nur Browser)
- **Output:** MKV-Format (crash-sicher, nachher zu MP4 remuxen)
- **Auflösung:** 1920×1080, 30 fps
- **Encoder:** x264 oder Hardware (NVENC/VAAPI), CRF 18-20
- **Audio:** Mikrofon nur aktivieren wenn live gesprochen wird, sonst stumm (Voiceover kommt nachher)
- **Hotkey:** Start/Stop-Recording auf eine Taste legen (z.B. F9)

---

## 2. Aufnahme-Drehbuch (Szene für Szene)

**Wichtig:** Jede Szene als **einzelnen Clip** aufnehmen — nicht versuchen alles in einem Take zu machen. Das erleichtert den Schnitt erheblich.

---

### Clip 1 — Intro/Cockpit (0:00–0:10)

**Startposition:** Browser offen, EEDC Cockpit/Dashboard geladen

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -3s | 3 Sekunden Vorlauf für Schnitt |
| Nichts tun | 3s | Cockpit wirken lassen |
| Maus langsam über die Key-Metrics bewegen | 5s | Autarkie, PV-Erzeugung, Netto-Ertrag |
| Recording stoppen | +2s | Nachlauf |

**Voiceover:**
> „EEDC — Energie Effizienz Data Center. Eine kostenlose, lokale PV-Analyse direkt in Home Assistant. Ich zeige euch in zwei Minuten, was das Tool kann."

---

### Clip 2 — Energiefluss-Diagramm (0:10–0:30)

**Startposition:** Sidebar sichtbar, „Live" noch nicht angeklickt

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Live" in Sidebar | 1s | Seite lädt |
| Warten | 8s | Animationen wirken lassen! Linien fließen. |
| Maus langsam über PV-Knoten → Haus → Batterie bewegen | 5s | Zeigt den Fluss visuell nach |
| Maus auf SoC-Anzeige rechts | 3s | |
| Maus auf Heute-kWh Werte rechts | 3s | |
| Recording stoppen | +2s | |

**Voiceover:**
> „Das Live-Dashboard zeigt in Echtzeit, wohin der Strom fließt. PV-Erzeugung, Batterie, Netz, Wallbox — alles als animiertes Flussdiagramm. Rechts seht ihr die Tages-kWh, Ladezustand und aktuelle Netzleistung."

**Tipp:** Dies ist die wichtigste Szene! Idealerweise aufnehmen wenn PV produziert UND Batterie lädt — dann sind mehrere Linien aktiv.

---

### Clip 3 — Tagesverlauf Butterfly-Chart (0:30–0:45)

**Startposition:** Noch auf Live-Seite

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Langsam nach unten scrollen zum Tagesverlauf | 2s | Smooth scrollen, nicht rucken |
| Warten | 3s | Chart wirken lassen |
| Maus über Chart bewegen (Tooltip erscheint) | 5s | Langsam von links nach rechts — zeigt Tagesverlauf |
| Auf einen Zeitpunkt hovern wo PV=hoch | 3s | Tooltip mit Werten zeigen |
| Recording stoppen | +2s | |

**Voiceover:**
> „Der Tagesverlauf zeigt das Energieprofil als Butterfly-Chart: Quellen oben, Senken unten. Man sieht sofort, wann die PV-Anlage produziert, wann der Speicher einspringt und wann aus dem Netz bezogen wird."

---

### Clip 4 — Aktueller Monat (0:45–1:15)

**Startposition:** Beliebig

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Cockpit" in Sidebar | 1s | |
| Warten | 3s | Übersicht wirken lassen |
| Maus über Energie-Bilanz Donut/Balken | 5s | |
| Maus über Autarkie-Wert | 2s | |
| Maus über Netto-Ertrag in € | 2s | |
| Nach unten scrollen zum Vorjahresvergleich | 2s | |
| Warten auf Vergleichsdaten | 5s | |
| Recording stoppen | +2s | |

**Voiceover:**
> „Im Cockpit der aktuelle Monat auf einen Blick: PV-Erzeugung, Autarkiequote, Netto-Ertrag in Euro. Die Energie-Bilanz zeigt Eigenverbrauch, Einspeisung und Netzbezug. Und direkt darunter der Vergleich zum Vorjahr — gleicher Monat, anderes Jahr."

---

### Clip 5 — Langzeit-Auswertung (1:15–1:45)

**Startposition:** Beliebig

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Auswertungen" in Sidebar | 1s | |
| Warten | 3s | Balkendiagramme laden |
| Maus über Monatsbalken hovern (Tooltips) | 5s | |
| Klick auf Tab „Finanzen" oder „PV-Anlage" | 1s | |
| Warten | 3s | Neue Charts laden |
| Maus über ROI oder Effizienz-Trend | 5s | |
| Recording stoppen | +2s | |

**Voiceover:**
> „Die Langzeit-Auswertung über alle Jahre: Energie-Bilanz pro Monat, Effizienz-Trends, spezifischer Ertrag pro kWp. Hier sieht man sofort, ob die Anlage performt oder ob etwas nicht stimmt."
>
> „Dazu Finanzauswertung mit ROI-Berechnung, CO₂-Einsparung und Komponenten-Vergleich."

---

### Clip 6 — Einstellungen/Setup (1:45–2:05)

**Startposition:** Beliebig

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Einstellungen" in Sidebar | 1s | |
| Klick auf „Sensor-Zuordnung" | 1s | |
| Langsam durch den Wizard scrollen | 5s | Zeigt die Sensor-Felder |
| Zurück zu Einstellungen | 1s | |
| Bereich „Cloud-Import" zeigen | 3s | Herstellerliste sichtbar |
| MQTT-Bereich zeigen | 3s | |
| Recording stoppen | +2s | |

**Voiceover:**
> „Die Einrichtung läuft über einen Wizard: Sensoren zuordnen, fertig. EEDC unterstützt direkte HA-Sensoren, MQTT für beliebige Smarthome-Systeme und Cloud-Import für elf Hersteller — SolarEdge, Fronius, Huawei, Growatt und mehr. Alles bleibt lokal, keine Cloud, keine Registrierung."

---

### Clip 7 — Community (2:05–2:20)

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Community" in Sidebar | 1s | |
| Warten | 3s | Benchmark-Daten laden |
| Maus über Vergleichstabelle/-chart | 5s | |
| Recording stoppen | +2s | |

**Voiceover:**
> „Optional: Anonymer Community-Vergleich. Wie steht meine Anlage im Vergleich zu anderen in der Region? Autarkie, spezifischer Ertrag, Eigenverbrauchsquote — alles anonymisiert."

---

### Clip 8 — Outro (2:20–2:30)

| Aktion | Timing | Detail |
|--------|--------|--------|
| Recording starten | -2s | |
| Klick auf „Live" in Sidebar | 1s | Zurück zum Energiefluss |
| Warten | 8s | Animationen laufen lassen |
| Recording stoppen | +2s | |

**Voiceover:**
> „EEDC — kostenlos, Open Source, läuft komplett lokal. Link zum GitHub-Repository in der Beschreibung. Feedback und Fragen gerne als Issue oder in den Kommentaren."

---

## 3. Voiceover aufnehmen

**Nach** dem Screen-Recording, nicht gleichzeitig.

| Aspekt | Empfehlung |
|--------|------------|
| **Mikrofon** | Headset reicht, kein Studio nötig. Abstand ~20cm |
| **Raum** | Ruhig, kein Hall (kleiner Raum, Teppich, Vorhänge helfen) |
| **Tempo** | Ruhig und gleichmäßig, nicht hetzen. Lieber Clips kürzen als schnell sprechen |
| **Aufnahme** | Pro Szene ein separates Audio-File (erleichtert Schnitt) |
| **Tool** | Audacity oder direkt Handy-Sprachmemo (Qualität reicht für YouTube) |

### Alternative: KI-Voiceover

Falls du nicht selbst sprechen willst:

- **ElevenLabs** (elevenlabs.io) — beste Qualität, 10 Min/Monat kostenlos
- **Google TTS** — kostenlos, klingt aber robotischer

---

## 4. Schnitt (DaVinci Resolve)

### Timeline-Aufbau

```
Video-Spur 1:  [Clip1][Clip2][Clip3][Clip4][Clip5][Clip6][Clip7][Clip8]
Audio-Spur 1:  [VO 1][VO 2 ][VO 3 ][VO 4 ][VO 5 ][VO 6 ][VO 7][VO 8]
Audio-Spur 2:  [————————————— Hintergrundmusik (leise) ——————————————————]
```

### Schnitt-Regeln

- **Übergänge:** Einfacher Cross-Dissolve (0.5s) zwischen Clips. Kein Fancy-Stuff.
- **Vorlauf/Nachlauf** der Clips abschneiden
- **Voiceover synchronisieren:** Audio an die passende Stelle schieben, Video-Clip ggf. kürzen/verlängern
- **Tempo:** Wenn eine Szene zu lang ist, Speed-Ramp auf 1.5× während Ladezeiten
- **Mauszeiger-Highlight:** Optional in OBS mit Plugin, oder nachträglich in Resolve

### Titel-Einblendungen

| Zeitpunkt | Text |
|-----------|------|
| 0:00 | **EEDC v3.1** (groß, mittig, 2s Fade) |
| 0:10 | *Live-Dashboard* (klein, unten links) |
| 0:45 | *Aktueller Monat* |
| 1:15 | *Langzeit-Auswertung* |
| 1:45 | *Setup & Datenquellen* |
| 2:05 | *Community-Benchmark* |
| 2:20 | **github.com/supernova1963/eedc-homeassistant** (mittig) |

### Hintergrundmusik

- **YouTube Audio Library** (studio.youtube.com → Audio Library): Lizenzfrei
- Suche nach: „ambient", „technology", „inspiring"
- **Lautstärke:** -20dB bis -25dB unter dem Voiceover
- Musik während Voiceover leiser (Ducking), in Pausen etwas lauter

---

## 5. Export & Upload

### Export-Einstellungen (DaVinci Resolve)

- **Format:** MP4 / H.264
- **Auflösung:** 1920×1080
- **Framerate:** 30fps
- **Bitrate:** 15-20 Mbps (YouTube re-encoded sowieso)

### YouTube Upload

- **Titel:** `EEDC — Kostenlose PV-Analyse für Home Assistant (Open Source)`
- **Beschreibung:**

```
EEDC (Energie Effizienz Data Center) — kostenlose, lokale PV-Analyse
als Home Assistant Add-on oder Standalone Docker.

GitHub: https://github.com/supernova1963/eedc-homeassistant
Standalone: https://github.com/supernova1963/eedc
Community: https://energy.raunet.eu
Docs: https://supernova1963.github.io/eedc-homeassistant/

Features:
- Live Energiefluss-Diagramm mit Animation
- Tagesverlauf (Butterfly-Chart)
- Monatsauswertung mit Vorjahresvergleich
- Langzeit-Analyse mit Effizienz-Trends
- MQTT-Inbound (funktioniert mit jedem Smarthome)
- Cloud-Import für 11 Hersteller
- Community-Benchmark (anonym)
- 100% lokal, keine Cloud, Open Source

#homeassistant #photovoltaik #solar #pv #energiemanagement #opensource
```

- **Tags:** `home assistant, photovoltaik, solar, pv, energiemanagement, opensource, eedc, pv-analyse, autarkie, eigenverbrauch`
- **Thumbnail:** Screenshot vom Energiefluss-Diagramm + Text-Overlay „EEDC v3.1" (in Canva oder direkt in Resolve)
- **Kategorie:** Science & Technology
- **Sprache:** Deutsch

---

## 6. Checkliste

- [ ] OBS installiert und konfiguriert
- [ ] EEDC läuft, Daten vorhanden, Dark Mode an
- [ ] Browser vorbereitet (sauber, Fullscreen, 1080p)
- [ ] Clip 1-8 aufgenommen (bei Sonnenschein!)
- [ ] Voiceover aufgenommen (8 Audio-Files)
- [ ] In DaVinci Resolve zusammengeschnitten
- [ ] Titel-Einblendungen eingefügt
- [ ] Hintergrundmusik unterlegt
- [ ] Exportiert als MP4 1080p
- [ ] YouTube-Upload mit Beschreibung und Tags
- [ ] Thumbnail erstellt und hochgeladen
