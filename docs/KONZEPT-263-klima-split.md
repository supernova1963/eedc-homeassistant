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
> **Offen:** **K-1** (SEER) · **K-2** (Heizen-vs-Kühlen-Trennung, der Kern) · **K-3** (PV-Anteil je Klima-Komponente). ⚠ **Harte Vorbedingung für K-2/K-3: eine Klimaanlage mit Betriebsmodus-Sensor bei einem Tester** — ohne sie wird die Hersteller-Vielfalt blind gebaut (dieselbe Lehre wie bei den Kompressor-Starts, #238).
>
> ⚑ **Die Vorbedingung ist am 2026-08-16 erstmals erfüllt** — kingcap1 (#263, 15.08.), Mitsubishi über MELCloud. **Am Bildmaterial gemessen, nicht aus der Beschreibung übernommen:** §„K-2 — Vermessung am ersten geeigneten Testgerät". Ergebnis in einem Satz: Der Modus ist da, **aber der kWh-Zähler trägt ihn nicht** — K-2 bleibt ein Bau, keine Auswertung vorhandener Felder. ⚑ **Nachtrag 16.08.:** Er hat die drei Rückfragen mit einem Selbstversuch beantwortet — **der Modus gehört der Anlage, nicht dem Innengerät** (§„K-2 Nachtrag"). Das verbilligt die Sensor-Seite, nicht die Aggregation.
>
> ⚠ **Der frühere Satz dieser Stelle ist zurückgezogen.** Er lautete: *„Ein Melder hat einen Modus-Sensor, misst aber drei Innengeräte über einen einzigen Zähler — damit ist K-2 nur zur Hälfte entsperrt"* (Stand 08.08.) und meinte dietmar1968. Der ist damit **falsch wiedergegeben**: Seine Antwort im Forum (#89667/92) lautete *„Zu 1: Es gibt nur entweder, oder"* — das ist eine Aussage über die **Anlage** (nicht gleichzeitig heizen und kühlen), nicht über einen auslesbaren Sensor. Das Fund-Register hatte denselben Post am 03.08. korrekt als **Gegenbeweis** eingeordnet („kein Betriebsmodus-Signal, keine Messung je Innengerät"). Die Roadmap **#110** trägt die falsche Lesart als „halb entsperrt" bis heute weiter — dort ungeprüft nachzuziehen, wenn #110 das nächste Mal angefasst wird.


Status: **Konzept, Issue bleibt offen.** Kein Code in dieser Etappe.
~~Entwurf für einen #263-Kommentar (Freigabe ausstehend).~~
✅ **Gepostet am 2026-08-17** ([`issuecomment-5318411323`](https://github.com/supernova1963/eedc-homeassistant/issues/263#issuecomment-5318411323), 18:00 UTC) — die
Quellcode-Erhebung zu den vier Anbindungen steht dort im Anwender-Text; ihre Messungen sind mit
diesem Nachzug hier eingearbeitet (Befund 1b). **Der Satz „Freigabe ausstehend" stand nach dem
Posten noch da** — dieselbe Klasse wie der Kopf-Block des Einstiegstextes, der die Anweisung „nicht
posten" weitertrug: *eine Zustandsangabe, die niemand beim Erledigen anfasst.*

## Maßnahmen-Register (fortschreibbar — Stand 2026-08-02)

| # | Maßnahme | Status | Notiz |
| --- | --- | --- | --- |
| **K-0** | Subtyp „Luft-Luft (Klimaanlage)" (`wp_art = luft_luft`) · SCOP-Modus · Stromsensor genügt · Daten-Checker ignoriert fehlende Heizwärme | ✅ seit v3.30.3, **Lücke geschlossen 2026-08-16** | Fundament steht. ⚠ **„Stromsensor genügt" galt bis 16.08. nur für den Daten-Checker:** `core/field_definitions.py::FELD_BEDARF` kannte die Wärmepumpen-**Art** nicht und stufte `heizenergie_kwh` für *jede* WP als Pflicht ein ⇒ *Einstellungen → Datenquellen* zeigte einer Klimaanlage „Heizwärme" rot und zählte sie als offene Pflicht, während der Checker dazu schwieg (Fund **N-86**). Diese Zeile behauptete „Fundament steht", ohne dass es jemand gegen den Code gehalten hatte. Jetzt trägt `get_feld_bedarf` den Geräte-Kontext (`KLIMA_OHNE_WAERMEMENGE`); Proben in `test_wp_klimaanlage_phase1.py` **an der Fläche**, mit Negativprobe für Luft-Wasser und für Altbestand ohne `wp_art` |
| **K-0b** | **Wegräumen, was es bei einer Klimaanlage nicht gibt:** keine Heizwärme-/Warmwasserbedarfs-Felder, keine konstruierte Ersparnis gegen Gas/Öl, keine daraus abgeleitete CO₂-Ersparnis — die Anlage wird als **Verbraucher** ausgewertet (Strom · PV-Anteil · Kosten) | ✅ gebaut 2026-08-02, ⚠ **Begründung 2026-08-16 korrigiert und Bauform ersetzt (K-0c)** | Die **unbeantwortete Hälfte des Issues** (3dmaster90: „Das sowas wie Warmwasser, Wärmebedarf etc. entfällt"). Einzige Maßnahme **ohne Testgerät**. Auslöser: das ROI-Dashboard wies rund **1.100 €/Jahr** und **2.210 kg CO₂** gegen eine nie ersetzte Gasheizung aus |
| **K-0c** | **Die Bewertung hängt an der Pflege, nicht an der Bauart:** neue Option `alter_energietraeger = "nichts"` („Nichts ersetzt (Neubau)"), kein erfundener Bedarfs-Default mehr, Typ-Sonderweg entfällt | ✅ gebaut 2026-08-16 | Der Nachfolger von K-0b — **und die Korrektur seiner Begründung**, s. Abschnitt unten. Löst zugleich **N-88** (jede WP im Neubau bekam eine Gaskessel-Ersparnis) und entschärft **N-91**. Layer-SoT `alternativkosten.py::ERSETZT_NICHTS` / `ersetzt_keine_heizung()` / `alle_ersetzen_nichts()`; Proben in `test_wp_ersetzt_nichts_n88.py` (Rechen-Ebene) und `test_roi_klimaanlage_nicht_bewertet.py` (Anzeige-Ebene) |
| **K-1** | **SEER** (Kühl-Effizienz) als Parameter | ⬜ | ~1–2 Tage. **Allein halbnützlich** — ohne K-2 ein Effizienz-Faktor ohne Bezugsgröße ⇒ **nicht zuerst bauen** |
| **K-2** | **Heizen-vs-Kühlen-Trennung** über Betriebsmodus-Sensor (+ Normalisierungs-Schicht, modus-gewichtete Aggregation, Serien-Split in 4 Read-Sites) | ⬜ **Kern, zuerst** — ⚑ **entsperrt, und seit 17.08. ist auch die Zielstruktur entschieden** | ~3–4 Tage + Live-Serien-Split (Schätzung von 08.08., **nicht** neu gemessen). **Sechs** Modus-Klassen statt eines Feldpaars; `hvac_action` wird **nicht** verlangt (Befund 1.1/1.2 + Vergleichstabelle 1b). **Bau unbeauftragt** |
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
- Stromverbrauchssensor reicht; Wärmemengenzähler optional (Klima-Realität) —
  ⚠ **auf der Zuordnungs-Fläche erst seit 2026-08-16**, s. K-0-Zeile (N-86).
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
⚑ **Seit 17.08. gilt die Sechs-Klassen-Struktur** (Befund 1.2); die zwei Feldnamen hier sind die
Kurzform von damals und nicht die Zielstruktur.

> ~~**Angrenzend, bewusst offen:** Auch eine klassische Wärmepumpe im **Neubau** ersetzt keine
> Heizung, bekommt aber weiterhin eine Gaskessel-Ersparnis angerechnet …~~
> ✅ **Erledigt mit K-0c am 2026-08-16** — das war **N-88** / F2(b), und es ist der Weg, der K-0b
> ablöst.

## K-0c — die Prämisse von K-0b war falsch, und mit ihr die Bauform (2026-08-16)

⛔ **Der Satz, auf dem K-0b stand, ist gefallen.** Er lautete: *„Eine Split-Klimaanlage ersetzt
keine Heizung."* **Das stimmt nicht** (Gernot, 16.08.): Eine Luft-Luft-Wärmepumpe **kann** sehr
wohl eine Gasheizung ersetzen, und viele Anwender heizen damit. Ob sie dafür die effizienteste
Bauart ist, ist eine andere Frage — und nicht die, die eedc an dieser Stelle beantwortet.

**Der Defekt, den K-0b behoben hat, war nie die Bauart, sondern eine erfundene Eingabe.** Fehlte
der Wärmebedarf, füllten ihn zwei Default-Schichten auf (12.000 kWh Heizwärme + 3.000 kWh
Warmwasser) ⇒ rund 1.100 €/Jahr und 2.210 kg CO₂ gegen eine Heizung, die es nie gab. K-0b hat das
an den **Typ** gebunden; das war der schnelle Weg und hat den Fall gelöst, aber die Klasse nicht —
genau so war es damals als **F2(a)** entschieden und als **N-88** mit Trigger geparkt
(`auftrag-n87-klima-roi-verbraucher.md` §F2). Gernots Einwand ist dieser Trigger.

⚠ **Zwei ausgelieferte Behauptungen waren dadurch unwahr und sind mit korrigiert:**

1. Der ROI-Hinweis und der Formular-Alert sagten beide: *„eine Ersparnis gegenüber Gas oder Öl
   weist eedc für Klimaanlagen nicht aus — dafür müsste das Gerät eine Heizung ersetzt haben und
   die Wärme gemessen sein."* **Beide Hälften trafen nicht zu.** eedc wies sie an fünf anderen
   Stellen sehr wohl aus (Cockpit, Aussichten, WP-Dashboard, Jahresbericht-PDF, HA-Sensor), und die
   genannte Bedingung war gar nicht die, an der die ROI-Zeile hängt: Die ist eine **Prognose aus
   gepflegten Parametern** (Bedarf × JAZ/COP), nicht die gemessene Ersparnis.
2. Der Code-Kommentar an der ROI-Fundstelle behauptete als Abgrenzung, *„die vier gemessenen Pfade
   liefern für dasselbe Gerät 0"*. Das galt nur, solange keine Wärme gepflegt war — der Schutz dort
   ist `wp_waerme_kwh <= 0`, keine Typ-Regel. Und **N-86 hat bis zum selben Tag dazu gedrängt**, die
   Heizwärme zu pflegen (rote Pflicht in der Zuordnungs-Fläche).

**Was K-0c stattdessen tut:**

- `alter_energietraeger` bekommt **„nichts ersetzt (Neubau)"** — die Angabe, die die Frage „hat
  dieses Gerät eine Heizung ersetzt?" überhaupt beantwortbar macht. Sie hängt an der
  **Installation**, nicht an der Bauart, und gilt für **jede** Wärmepumpenart.
- Der **erfundene Bedarfs-Default entfällt**. Ohne gepflegten Bedarf steht „nicht bewertet" mit dem
  Weg heraus. Auch die halbe Pflege rechnet ehrlich (nur Warmwasser gepflegt ⇒ Heizwärme 0 statt
  12.000 — ein Restfall, den erst ein **stummer Sprengsatz** sichtbar gemacht hat).
- Die **Bedarfsfelder werden für `luft_luft` wieder angezeigt**, weiterhin **ohne Vorbelegung**.
  Nebenwirkung, bewusst: Damit ist **N-91** entschärft — eine bei einem Typwechsel im offenen
  Formular übernommene Vorbelegung ist jetzt sichtbar und korrigierbar.
- **Bestandsschutz ohne Migration:** Steht an einer Luft-Luft-WP noch **exakt** die unveränderte
  Vorbelegung (12.000/3.000), zählt sie als offene Frage, nicht als Antwort — der Anwender konnte
  sie seit K-0b weder sehen noch ändern. Befund plus Weg heraus statt einer Migration, die rät
  ([[feedback_kein_grosser_heiler_knopf]]). Bei klassischen Wärmepumpen bleibt die Vorbelegung eine
  brauchbare Schätzung und wird unverändert gerechnet — dort war sie immer sichtbar.

⚠ **Was K-0c bewusst NICHT löst:** In den **anlagenweit aggregierten** Sichten (Jahresbericht-CO₂,
Aussichten-Jahresprognose) ist die Wärme über alle Geräte summiert. Dort entfällt der fossile
Vergleich erst, wenn **keine einzige** WP etwas ersetzt hat (`alle_ersetzen_nichts`). Steht neben
einer Neubau-WP eine zweite, die eine Gasheizung ersetzt hat, wird weiterhin die gesamte Wärme
verglichen. Sauber wäre eine Trennung je Gerät in der Aggregation selbst; sie berührt Cockpit,
Komponenten-Zeitreihe, Aussichten, HA-Export und den Jahresbericht und ist ein eigenes Paket. **So
herum verschlechtert sich für niemanden etwas**, und die per-Gerät-Pfade sind exakt.

## K-2 — Vermessung am ersten geeigneten Testgerät (2026-08-16)

**Quelle:** kingcap1 (Glen), [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263)
vom 15.08.2026, sechs Screenshots. **Alle sechs geladen und angesehen** — die Angaben unten sind an
den Bildern abgelesen, nicht aus seinem Text übernommen.

**Aufbau:** Mitsubishi Electric über die **MELCloud**-Integration, **ein** Außengerät und **drei**
Innengeräte (*GC-Büro* · *Vic-SZ* · *Wohnzimmer*), je Gerät **vier** Entitäten. Daneben ein
**Shelly 1PM** am Außengerät als eigene Messung, sowie ein **zweites Fabrikat** im Haus
(`EinhellKlimaSZ-IP168`, eigene Steckdosenmessung).

### Befund 1 — der Modus ist auslesbar, aber nur als eigene Entität

Die `climate`-Entität je Innengerät führt sechs Modi: **Heizen/Kühlen · Heizbetrieb · Kühlbetrieb ·
Entfeuchtung · Nur Lüftung · Aus**. Damit ist die harte Vorbedingung erfüllt — erstmals.

⚠ **Zwei Einschränkungen, beide für K-2 teuer:**

1. Das ist der **eingestellte** Modus (`hvac_mode`), nicht der Ist-Betrieb. Der erste Eintrag,
   **„Heizen/Kühlen"**, ist die Automatik: Steht das Gerät darauf, sagt der eingestellte Modus
   nichts darüber, was es gerade tut. Dafür bräuchte es `hvac_action` (heating/cooling/idle) —
   **ob MELCloud das liefert, ist aus dem Bildmaterial nicht ablesbar und damit offen.**

   > ✅ **ENTSCHIEDEN am 2026-08-17, am Quellcode statt am Bildmaterial:** **MELCloud liefert es
   > für dieses Gerät nicht.** In `homeassistant/components/melcloud/climate.py` (HA-Core, Branch
   > `dev`) definiert **nur** `AtwDeviceZoneClimate` — die **Luft-Wasser**-Klasse — eine
   > `hvac_action`-Property; `AtaDeviceClimate` (Luft-Luft, also die Splitgeräte des Melders) und
   > die gemeinsame Basisklasse `MelCloudClimate` haben sie **nicht**. Damit ist die Frage nicht
   > „noch nicht ablesbar", sondern beantwortet: **eedc kann bei MELCloud-Splitgeräten nur den
   > eingestellten Modus sehen.**
   >
   > ⇒ **Folge für den Bau, und sie ist keine Blockade:** `hvac_action` wird **nicht verlangt**.
   > Wo es da ist (Daikin, s. Tabelle), verfeinert es; wo nicht, gilt der eingestellte Modus. Die
   > Automatik-Stellung „Heizen/Kühlen" wird dann **nicht geraten**, sondern als eigene Klasse
   > *unbestimmt* geführt (s. Punkt 2) — die P4-Linie: eine Antwort, die weniger enthält als sie
   > soll, sagt es selbst.
2. Es sind **nicht zwei Klassen, sondern mindestens vier**: *Entfeuchtung* und *Nur Lüftung* sind
   weder Wärme noch Kälte. Das im Baustein-2-Abschnitt genannte Feldpaar
   `strom_heizen_kwh`/`strom_kuehlen_kwh` würde diesen Strom stillschweigend einer der beiden
   Seiten zuschlagen. **Die Zielstruktur ist damit offen** und gehört vor den Bau entschieden.

   > ✅ **ENTSCHIEDEN am 2026-08-17 (Gernot): SECHS Klassen** —
   > `heizen` · `kuehlen` · `entfeuchten` · `lueften` · `aus` · `unbestimmt`.
   > Die sechste ist der Grund, warum es keine fünf sind: Automatikbetrieb ohne `hvac_action`
   > erzeugt Zeit, die **keiner** Seite zusteht. Sie einer zuzuschlagen wäre eine erfundene
   > Aufteilung; sie wegzulassen machte die Summe unvollständig, ohne es zu sagen.
   > ⇒ Das Feldpaar `strom_heizen_kwh`/`strom_kuehlen_kwh` aus dem Baustein-2-Abschnitt ist damit
   > **überholt**; die Zielstruktur trägt sechs Größen. Vor dem Bau ist damit nichts mehr offen.

### Befund 1b — was die Anbindungen tatsächlich herausgeben (2026-08-17, am Quellcode erhoben)

**Warum diese Tabelle hier steht:** Die Normalisierungs-Schicht wurde bis dahin mit *einem*
Anwender begründet, der zwei Fabrikate betreibt. Die Erhebung zeigt, dass die Unterschiede
**zwischen** den Anbindungen größer sind als zwischen den Geräten — und dass ausgerechnet der
Ist-Betrieb die seltene Ausnahme ist. Jede Zeile ist an der Quelle belegt, nicht aus dem
Gedächtnis; wo ein Beleg fehlt, steht das als solches da.

| Anbindung | Modi (`hvac_mode`) | Ist-Betrieb (`hvac_action`) | Energie je Gerät | Beleg |
| --- | --- | --- | --- | --- |
| **MELCloud** (Mitsubishi, HA-Core) | ja | **nein** für Luft-Luft | ja, ein modus-blinder kWh-Zähler | `melcloud/climate.py`: `hvac_action` **nur** in `AtwDeviceZoneClimate` (Luft-Wasser), nicht in `AtaDeviceClimate`/`MelCloudClimate` |
| **Daikin** (Original-WLAN-Modul, HA-Core) | ja | **ja** — und differenziert | modellabhängig | `daikin/climate.py::DaikinClimate.hvac_action`: liefert `IDLE`, wenn `support_compressor_frequency` **und** `compressor_frequency == 0` — also „eingeschaltet, aber läuft gerade nicht" |
| **Bosch HomeCom Easy** (Climate 3000i/5000i/6000i, HACS `serbanb11/bosch-homecom-hass`) | ja (`off · auto · heat · cool · dry · fan_only`) | **nein** | **keiner** — Messsteckdose nötig | `climate.py`: `BoschComRacClimate` setzt kein `hvac_action`; nur die Kessel-Klasse `BoschComK40Climate` tut es. `sensor.py`: für `deviceType == "rac"` entsteht **genau eine** Entität — `BoschComSensorNotificationsRac` |
| **Faikout** (ESP32 am S21-Bus, ehem. Faikin) | ja | **nicht belegt** | **ja**, MQTT-Feld `Wh`, kumulativ, Auflösung **100 Wh** | Maintainer-Aussage (RevK); **keine** Momentanleistung über S21. ⚠ Als einzige Zeile nicht am Code nachgeprüft — Quelle ausdrücklich benannt |

⚑ **Drei Lehren für den Bau, jede aus einer Zeile:**

1. **`hvac_action` darf keine Voraussetzung sein** — genau die verbreitetste Anbindung im Feld
   (MELCloud) hat es für Splitgeräte nicht. Wer es verlangt, baut für Daikin und sperrt den Rest aus.
2. **„Kein Energiesensor" ist ein realer Fall, kein Randfall** (Bosch RAC). Die Mengengröße kommt
   dort aus einer **Messsteckdose** — also aus einer Quelle, die vom Modus-Signal getrennt ist und
   die eedc über die normale Zuordnungsfläche schon kennt.
3. **Auflösung ist eine eigene Größe**: 100-Wh-Schritte (Faikout) sind für Monatswerte reichlich,
   für eine minutengenaue Modus-Gewichtung grob. Das gehört in die Normalisierungs-Schicht, nicht
   in die Read-Sites.

### Befund 2 — der kWh-Zähler je Innengerät ist modus-blind

Je Innengerät gibt es genau **einen** Zähler, *Energieverbrauch* in kWh. Abgelesen:

| Innengerät | Modus zum Zeitpunkt des Bildes | Energieverbrauch |
| --- | --- | --- |
| Vic Schlafzimmer | Aus | 39,90 kWh |
| GC Büro | **Kühlbetrieb** | 4.115,70 kWh |
| Wohnzimmer | Aus | 77,60 kWh |

Heizen und Kühlen laufen in **dieselbe** Zahl. Es gibt keinen Heiz- und keinen Kühl-Zähler.

⇒ **Konsequenz für den Bau:** eedc kann den Split nicht aus vorhandenen Feldern lesen, sondern muss
den Modus **zur Snapshot-Zeit** mitschreiben und den kWh-Zuwachs des Intervalls dem dann geltenden
Modus zuschlagen — genau die modus-gewichtete Aggregation, die der Baustein-2-Abschnitt beschreibt.
Der Aufwand dort steht damit, er schrumpft durch das Testgerät **nicht**.

### Befund 3 — die Innengeräte-Zähler sind ohne Klärung nicht verwertbar

kingcap1 misstraut den Werten selbst („bei WZ finde ich, dass er viel zu wenig anzeigt"). Am Bild
gemessen ist die Abweichung **größer als sein Verdacht**: Sein Shelly am Außengerät
(`KlimaSplitMitsubishi-IP179`) meldet für **2026 insgesamt 1.103,2 kWh** — das Büro-Innengerät
allein steht bei **4.115,70 kWh**, mehr als das Vierfache der Anlagensumme desselben Zeitraums.

⚠ **Plausibelste Lesart, nicht belegt:** der Innen-Zähler ist ein Lebensdauer-Zähler, der Shelly
ein Jahresfilter. Aus dem Bildmaterial ist das **nicht** entscheidbar — es wäre eine Rückfrage an
ihn (Zeitraum-Bezug beider Zahlen).

⇒ **Konsequenz:** Die belastbare Mengengröße ist der **Zähler am Außengerät**. Die
Innengeräte-Zähler taugen allenfalls als **Verteilschlüssel**, und auch das erst nach der
Klärung. **K-3 (Aufteilung je Innengerät) bleibt damit zu** — daran ändert dieses Testgerät nichts.

### Was aus der Vermessung folgt

- **K-2 ist entsperrt**, aber unverändert ein ~3–4-Tage-Bau plus Live-Serien-Split. Vorher zu
  entscheiden: die Zielstruktur der Modus-Klassen (Befund 1.2) und ob `hvac_action` verlangt wird
  oder der eingestellte Modus genügt (Befund 1.1).

  > ✅ **Beide Punkte sind am 2026-08-17 entschieden** (s. die Vermerke bei Befund 1): **sechs
  > Klassen** und **`hvac_action` wird nicht verlangt**. **Vor K-2 ist damit nichts mehr offen** —
  > was bleibt, ist der Bau selbst, und der ist **unbeauftragt**. ⚠ Die Aufwandsangabe oben ist
  > seit dem 2026-08-16 **nicht** neu gemessen worden; sie ist eine Schätzung, keine Zusage.
- **K-3 bleibt zu** (Befund 3).
- **K-1 (SEER) bleibt hinter K-2**, unverändert.
- Die **Normalisierungs-Schicht ist keine Vorsichtsmaßnahme**, sondern schon an diesem einen
  Anwender belegt: Er betreibt Mitsubishi **und** Einhell.

### K-2 Nachtrag — die drei Rückfragen sind beantwortet (2026-08-16, kingcap1)

**Quelle:** [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263), drei Kommentare
vom 16.08.2026 (11:51 · 12:03 · 12:16). Er hat die drei Rückfragen aus dem Kommentar desselben Tages
beantwortet **und dafür an seiner Anlage einen Selbstversuch gefahren**. Die Antworten ändern zwei
der drei Befunde oben — deshalb hier als Nachtrag statt als stille Korrektur.

**Zu Rückfrage 2 (Betriebszustand) — die wichtigste Antwort, und er hat sie nicht als Befund
gemeldet:** Er hat ein Innengerät auf *Heizen* gestellt, während die übrigen kühlten. Ergebnis:
**Das Gerät tut nichts** — Klappe zu, Kontrollleuchte blinkt. Zurück auf *Kühlen* läuft es sofort
wieder. Seine eigene Einordnung: „entweder bei ALLEN Innen nur Kühlen oder bei ALLEN Innen nur
Heizen … sonst müsste man ja mind. 2 Kreisläufe haben (also 4 Rohre zu jedem Innen)".

⇒ **Der Betriebsmodus ist eine Eigenschaft der Anlage, nicht des Innengeräts.** Für den Bau ist das
eine Vereinfachung, und zwar an der teuersten Stelle: **ein** Modus-Signal je Außengerät genügt, und
es passt genau auf die Mengengröße, die nach Befund 3 als einzige belastbar ist — den Zähler am
Außengerät. Die modus-gewichtete Aggregation aus Baustein 2 braucht damit **keine** Zuordnung
Modus↔Innengerät.

⚠ **Die Grenze gehört dazu, sie ist nicht gemessen, sondern Bauart:** Das gilt für
**2-Rohr-Systeme** — den Regelfall im Wohnhaus, und er nennt die Begründung selbst. Eine
3-Rohr-Anlage mit Wärmerückgewinnung kann gleichzeitig heizen und kühlen. Eine Bauform, die den
Modus nur an der Anlage kennt, ist für diesen Fall zu eng; das gehört vor dem Bau entschieden, nicht
danach entdeckt.

⚠ **`hvac_action` bleibt offen.** Er hat es nicht bestätigt („es gibt sicher ein besseres
MELCloud-MQTT-Addon, was mehr auslesen kann"). **Befund 1.1 steht also unverändert** — aber er wiegt
weniger, weil die Automatik „Heizen/Kühlen" bei einer Anlage mit *einem* Modus ohnehin nur eine
Betriebsart der ganzen Anlage sein kann.

> ✅ **Überholt am 2026-08-17 — nicht durch eine Melder-Antwort, sondern am Quellcode:** Die Frage
> ist **entschieden**, `AtaDeviceClimate` hat kein `hvac_action` (Befund 1.1). Sein Hinweis auf ein
> „besseres MQTT-Addon" ändert daran nichts: die Integration gibt heraus, was die Klasse definiert.
> ⇒ Die Formulierung „bleibt offen" gilt nicht mehr; offen war sie, solange nur Bildmaterial vorlag.

**Zu Rückfrage 3 (Entfeuchtung / Nur Lüftung): „NEIN, wir nutzen eigentlich nur Kühlen oder
Heizen."** Bei erreichter Zieltemperatur drosselt die Automatik den Luftstrom — bewusst auf Lüftung
stellt er nicht. ⇒ **Befund 1.2 entschärft sich für die Praxis, entfällt aber nicht:** zwei Klassen
plus eine benannte Restklasse reichen. Ein Feldpaar `strom_heizen_kwh`/`strom_kuehlen_kwh` **ohne**
dritte Zeile bleibt trotzdem falsch, weil es den Reststrom einer der beiden Seiten zuschlägt. Belegt
ist die Aussage für **einen** Haushalt.

**Zu Rückfrage 1 (Zeitbezug) — die Klärung kommt, aber sie rettet Befund 3 nicht:** Der Shelly ging
„quasi am gleichen Tag online" wie die Anlage (Anfang 2024) und steht **insgesamt bei 3.190 kWh**;
die 1.103,2 kWh aus der Vermessung sind der 2026er-Ausschnitt davon. Zum Zeitbezug der
MELCloud-Zahlen kann er nichts sagen — er hatte im **August 2025 einen HA-Crash ohne Recovery**.

⇒ ⚑ **Die naheliegende Erklärung ist damit widerlegt, nicht bestätigt.** „Innen = Lebensdauer,
Shelly = Jahresfilter" trägt nicht: Das Büro-Innengerät allein steht bei **4.115,70 kWh** und damit
über dem **Lebensdauer**-Wert der ganzen Anlage (3.190 kWh). Auch Lebensdauer gegen Lebensdauer geht
die Rechnung nicht auf. ⚠ **Entscheidbar ist es weiterhin nicht** — der HA-Crash kann die
Shelly-Historie beschnitten haben, der Zähler im Gerät ist davon unberührt. **Befund 3 bleibt
bestehen, K-3 bleibt zu**, und die Innengeräte-Zähler taugen bis auf Weiteres **nicht einmal** als
Verteilschlüssel.

**Was das für die Reihenfolge heißt:** Nichts. K-2 bleibt der Kern und bleibt ein ~3–4-Tage-Bau —
der Modus-Befund macht die Sensor-Seite billiger, nicht die Aggregation. Zu entscheiden ist vor dem
Bau weiterhin die Zielstruktur der Modus-Klassen (jetzt: zwei plus Rest) und ob der eingestellte
Modus genügt.

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
  ⚑ **Präzisiert 16.08. (K-2 Nachtrag):** **ein** Signal je Investition/Außengerät
  genügt — der Modus ist bei 2-Rohr-Systemen eine Anlagen-Eigenschaft, und er
  passt damit auf denselben Bezug wie der einzige belastbare Zähler. **Keine**
  Zuordnung Modus↔Innengerät nötig.
- Modus-gewichtete Aggregation: Stromverbrauch je Modus getrennt in
  `verbrauch_daten` (z. B. `strom_heizen_kwh` / `strom_kuehlen_kwh`),
  Snapshot-Aggregator schreibt pro Modus.
  ⚑ **Präzisiert 17.08.: es sind SECHS Größen, nicht zwei** — `heizen` · `kuehlen` ·
  `entfeuchten` · `lueften` · `aus` · `unbestimmt` (Entscheid Gernots, s. Befund 1.2).
  Das Feldpaar oben war die Fassung von vor der Vermessung; **wer nur zwei Felder schreibt,
  schlägt den Rest still einer Seite zu.** `unbestimmt` trägt die Automatikzeit ohne
  `hvac_action` — sie wird ausgewiesen, nicht verteilt.
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
