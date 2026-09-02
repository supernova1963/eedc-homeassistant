# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** hier bewusst **keine Zahl** — Versions-SoT ist [CHANGELOG.md](CHANGELOG.md) (oberster released Abschnitt) bzw. `eedc/backend/core/config.py::APP_VERSION`. `release.sh` bumpt CLAUDE.md **nicht**; eine Zahl an dieser Stelle veraltet daher garantiert (sie stand bis 2026-07-27 auf 3.45.5, während v4.0.1 released war).

## Verbundene Repositories

| Repository | Zweck | Technik |
| --- | --- | --- |
| **eedc-homeassistant** (dieses) | Source of Truth, HA-Add-on, Website, Docs | FastAPI, React, SQLite |
| **[eedc](https://github.com/supernova1963/eedc)** | Standalone-Distribution für Nutzer ohne HA | Spiegel von eedc/ |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server | FastAPI, React, PostgreSQL |

**Lokale Pfade:**
- eedc: `/home/gernot/claude/eedc`
- eedc-community: `/home/gernot/claude/eedc-community`

**Live:** https://energy.raunet.eu (Community) | https://supernova1963.github.io/eedc-homeassistant/ (Website)

## Git-Workflow (WICHTIG – gilt für alle Sessions und Rechner!)

### Regeln

1. **Immer auf `main` arbeiten** — keine Feature-Branches. Einzelentwickler-Projekt.
2. **eedc-homeassistant ist Source of Truth** — ALLE Änderungen (backend, frontend, docs, HA-Config) hier machen. Nie direkt in `eedc`.
3. **`eedc`-Repo wird nur per Release-Script synchronisiert** — kein manuelles Editieren, kein Subtree.
4. **Versionsnummern + Release** nur wenn der User es explizit anfordert.
5. **`eedc-community`** ist unabhängig, aber bei Datenmodell-Änderungen beide Repos synchron anpassen.

### Verboten!

- **Direkt im `eedc`-Repo arbeiten** — das ist nur ein Spiegel, wird per Script synchronisiert
- **`git subtree pull/push`** — wird nicht mehr verwendet
- **Releases, Tags, Versionsnummern ändern** — nur auf explizite User-Aufforderung
- **`git push`** — nur auf User-Aufforderung oder über `scripts/release.sh`

### Verzeichnisstruktur

```text
eedc-homeassistant/           ← Source of Truth
├── eedc/                     ← Gesamte Anwendung
│   ├── backend/              ← FastAPI Backend (Python)
│   ├── frontend/             ← React Frontend (TypeScript)
│   ├── Dockerfile            ← HA-spezifisch (mit Labels, jq, run.sh)
│   ├── config.yaml           ← HA Add-on Konfiguration
│   ├── run.sh                ← HA Container-Startscript
│   ├── icon.png / logo.png   ← HA Add-on Icons
│   ├── CHANGELOG.md          ← Kopie von Root (per Script)
│   ├── docker-compose.yml    ← Für Standalone-Nutzung
│   └── README.md             ← Projekt-README
├── website/                  ← Astro Starlight Website
├── scripts/                  ← Release + Utility Scripts
├── docs/                     ← Single Source of Truth für Dokumentation
├── CHANGELOG.md              ← Master-CHANGELOG (hier editieren!)
├── CLAUDE.md
└── repository.yaml
```

## Quick Reference

### Entwicklungsserver starten

```bash
# Backend (Terminal 1)
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd eedc/frontend && npm run dev

# URLs: Frontend http://localhost:3000 | API Docs http://localhost:8099/api/docs
```

### Gates (vor jedem Commit-Paket vollständig laufen lassen)

```bash
# Backend — EINE Zone (Europe/Berlin), parallelisiert. Diese Box IST die Berlin-Abdeckung;
# UTC und Pacific/Auckland fährt `tests.yml` bei jedem Push selbst (Zeile 71 und 84f.).
# ⛔ `-n 3` ist an die EINE Zone gekoppelt und nur dann ein Gewinn: drei Zonen sättigen die
#   vier Kerne bereits, mit je `-n 3` würde es langsamer und nacheinander (3 × 62 s) schlechter
#   als die 156 s von heute. Entweder drei Zonen ODER xdist — nicht beides.
cd eedc && source backend/venv/bin/activate
python -m pytest backend/tests -q -n 3

# Frontend — lint ZUERST (CI ruft ESLint mit --max-warnings 0), tsc OHNE Pipe
cd eedc/frontend && npm run lint
cd eedc/frontend && npx tsc --noEmit          # nie durch `| tail` — $? misst sonst tail
cd eedc/frontend && npm run test              # faehrt seit E8/M14 ALLE 25 Quelltext-check:* mit

# ⛔ Die frueher hier stehende `for s in check:*`-Schleife ist mit E8/M14 ENTFALLEN (24.08.).
# Sie lief 25 Pruefer ein zweites Mal, die `npm run test` darueber schon gefahren hat — genau
# der Doppellauf, den dasselbe Paket aus `tests.yml` entfernt hat, nur lokal. Seit M14 hat
# JEDER check:* aus package.json einen Vitest-Wrapper unter `src/test/`; dass das so bleibt,
# haelt `src/test/check-einhaengung.test.ts` fest (er meldet rot, sobald einer von `npm test`
# aus nicht mehr erreichbar ist). Ein rot gemeldeter Pruefer wird im Vitest-Protokoll beim
# Namen genannt — die Schleife lieferte nichts, was dort fehlt.
# Ausgenommen bleiben `park-leertest` und `chart-audit`: sie brauchen eine laufende Box und
# stehen im eigenen Kasten unter der Liste.

# Braucht dieses Paket den Park-Livetest? (Auslöser statt Takt — s. Kasten unten)
# ⛔ Seit 24.08. (Gernot) zählt das HINZUFÜGEN eines Park-Elements, nicht das blosse
#   VORKOMMEN eines Park-Bezeichners. Testdateien und Kommentare zählen nicht.
# ⛔ Der frühere EINZEILER an dieser Stelle maß etwas anderes als die Regel sagt und ist
#   am 02.09. durch das Skript ersetzt: Er zählte Park-Bezeichner in **hinzugefügten
#   Diff-Zeilen** — und eine GEÄNDERTE Zeile ist im Diff eine hinzugefügte. Über die
#   letzten 150 Commits gemessen: **3 Auslösungen, alle 3 falsch, null echte.** An den
#   drei historischen Belegfällen liefert das Skript exakt dieselben Werte (5/0/0), es
#   verliert also keine Deckung. **Dritte Runde derselben Klasse** — 1. Fassung Ermessen,
#   2. „Datei enthält", 3. „Zeile enthält", jetzt: die MENGE der Park-Elemente wächst.
# ⚠ Basis ist HEAD, NICHT origin/main: Gates laufen VOR dem Commit, und `origin/main` würde
#   alle bereits geprüften ungepushten Commits mitschleppen (am 23.08. beim Bau der Regel selbst
#   passiert — sie meldete eine Park-Berührung aus `566635a2` für ein reines Doku-Paket).
#   Umfasst das Paket schon Commits, entsprechend `HEAD~n` als Argument übergeben.
cd /home/gernot/claude/eedc-homeassistant
./scripts/park-ausloeser.sh          # Exit 1 ⇒ Park-Leertest fahren; Exit 0 ⇒ nicht fällig

# Doku-Spiegel ans ENDE, danach inhaltlich per diff prüfen (nicht nur Exit-Code)
./scripts/sync-help.sh && cd website && npm run build
```

> ⚠ **Ein Prüfer zählt sich nicht selbst — eine Gegenprobe gehört dazu.** Ein grüner Lauf
> beweist nur dann etwas, wenn der Prüfer rot melden *kann*: für `check:design` muss der
> Sprengsatz **außerhalb** `lib/colors.ts` sitzen (dort ist die Hex-Farbe erlaubt, die Gegenprobe
> greift sonst nicht — gemessen 11.08.). Rückbau per **Dateikopie**, nie `git checkout --`, wenn
> ungecommittete Arbeit im Baum liegt.

> ⚠ **`npm run lint` gehört dazu, seit der CI-Lauf zu v4.0.13 daran gescheitert ist** (12.08.): Der Workflow ruft ESLint mit `--max-warnings 0` auf, die Liste hier kannte ihn nicht — eine `react-hooks/exhaustive-deps`-**Warnung** aus `62c680b9` lief damit durch alle lokalen Gates und machte den Tests-Lauf **nach** dem Push rot. Ein Prüfer, den nur CI kennt, fällt zwangsläufig zu spät auf.
>
> ⚠ **Bei allem Zeitbezogenen zusätzlich `TZ=UTC python -m pytest backend/tests -q` fahren** — seit dem CI-Lauf zu v4.0.14 (13.08.): **Diese Box steht in `Europe/Berlin`, der GitHub-Runner in UTC.** Zwei Fälle aus `test_scheduler_publish_takt.py` waren lokal grün und in CI rot, ohne dass am Produktcode etwas fehlte: `CronTrigger` ohne `timezone`-Argument rechnet in der Zone des **Prozesses**, derselbe korrekte Feuerzeitpunkt heißt dort 10:00:05 und hier 08:00:05. **Ein grüner lokaler Lauf ist auf dieser Box kein grüner CI-Lauf.** Dieselbe Klasse wie der `lint`-Befund darüber — ein Prüfer, den nur CI kennt. ⚑ **Seit 23.08. steht eine DRITTE Zone daneben, und das ist die Antwort auf N-167** — Proben, die die echte **Uhr** statt einer gestellten lesen (vier von 24 Stunden rot ohne Code-Änderung). Berlin und UTC trennen nur **zwei** Stunden; eine stundenabhängige Wette kann darin dauerhaft unentdeckt bleiben. `Pacific/Auckland` liegt 10–12 Stunden entfernt, trifft verlässlich eine andere Stunde und regelmäßig einen anderen **Tag**. ⚠ **Sie läuft auch in CI** (`tests.yml`, zweiter pytest-Schritt) — eine Zeile, die nur in dieser Liste steht, ist eine Gedächtnisstütze und kein Wächter; genau der `lint`-Befund von oben, nur in der Gegenrichtung. ⭐ **Die Arbeitsteilung, am 23.08. erstmals gemessen:** CI fährt **UTC** (Runner-Default) **und Auckland** bei jedem Push, der `eedc/backend/**` oder `eedc/frontend/**` berührt — **`Europe/Berlin` läuft NUR hier**, diese Box *ist* die Berlin-Abdeckung. ⛔ **Hier stand bis 2026-08-24: „Trotzdem alle drei lokal, und zwar parallel — nacheinander 460 s, parallel 169 s, gegenüber einer einzigen Zone (168 s) also eine Sekunde."** **Diese Zahl war falsch, und sie hat achtzehn Tage lang eine Entscheidung getragen, die sie nicht tragen konnte.** Am 24.08. neu gemessen, kalt und warm identisch: drei Zonen parallel **156 s**, eine Zone **126 s** — die Differenz ist **31 s, nicht 1 s**. Der Parallelwert von damals stimmt fast auf die Sekunde; auseinander läuft nur die **Grundlinie** (168 gegen 126), sie wurde offenbar unter Last erhoben. *Eine Vergleichszahl ist nur so gut wie ihre Grundlinie — wer eine Differenz notiert, notiert beide Messungen und die Bedingungen.* ⭐ **Die Folge (Entscheid Gernot, 24.08.): lokal nur noch `Europe/Berlin`, dafür mit `-n 3` (126 s → 62 s).** UTC und Auckland laufen ohnehin in CI, lokal geht also **keine Abdeckung** verloren — nur die Zuordenbarkeit eines zonenspezifischen Fehlschlags zu einem einzelnen ungepushten Commit. ⛔ **Die Kopplung gehört dazu:** `-n 3` zahlt sich **nur** bei einer Zone aus. Drei Zonen sättigen die vier Kerne bereits; mit je `-n 3` wird es langsamer, nacheinander mit `-n 3` sind es 3 × 62 = 186 s und damit schlechter als heute. **Gegenprobe gefahren** (23.08.): ein Test, der nur in Auckland fällt, macht das Sammel-Ergebnis rot — die Auswertung fragt jeden Prozess einzeln ab. **Am 23.08. über sieben Zonen gemessen** (Berlin · UTC · Bogotá 00:11 · Kolkata · Auckland · Honolulu · Marquesas): kein Fehlschlag, sechs verschiedene lokale Stunden, beide Seiten eines Datumswechsels — die Stichprobe enthält mit **05:00 und 17:00** zwei der vier Stunden des Ursprungsfalls, hätte ihn also gefangen. ⚠ **Was sie NICHT erreicht:** die Kalenderkanten (Monatsende, Jahreswechsel, Schaltjahr, Zeitumstellung) — dafür bräuchte es eine gestellte Uhr (`freezegun`). ⛔ **Am 23.08. entschieden (Gernot): `freezegun` wird NICHT aufgenommen** — auch nicht als reine Dev-Abhängigkeit. Die Kalenderkanten bleiben damit ungemessen, und das ist die getroffene Wahl, **keine offene Frage und keine Vertagung**. Hier stand bis dahin „bewusst nicht entschieden" — genau diese Formulierung hat die Frage in jeder neuen Sitzung erneut aufgemacht. **Nicht neu aufrollen**; wer es doch will, bringt eine neue Messung mit, nicht das alte Argument.

> ### ⛔ Die Zeitzone der App wird NICHT festgenagelt (Entscheid Gernot, 2026-08-24)
>
> **Frage war:** eedc ist ein DACH-Produkt und wird nie international — warum nicht beim Start
> alles hart auf `Europe/Berlin` heben und die Zonenfrage damit erledigen?
>
> **Antwort: weil beide Auslieferungswege die Zone bereits setzen und ein Checker den Rest
> abfängt. Es gäbe niemanden zu retten.** Gemessen am 24.08.:
>
> * **Standalone** — `docker-compose.yml:11` setzt `TZ=Europe/Berlin`.
> * **HA-Add-on** — der Supervisor reicht die in HA eingestellte Zone durch. Das steht nicht nur
>   in der HA-Doku, sondern im eigenen Produkt: der Daten-Checker sagt es dem Anwender wörtlich
>   („Das Add-on übernimmt die Zeitzone beim Start von Home Assistant").
> * **Abweichung** — `daten_checker/datenquelle.py` (Kategorie `ZEITZONE_ABWEICHUNG`) holt
>   `/config` von HA, vergleicht `time_zone` mit der eigenen und warnt samt Reparaturweg.
>
> **Was die Prozesszone überhaupt entscheidet, und was nicht.** HA liefert absolute
> Unix-Zeitstempel (`start_ts` aus der recorder-DB) — die sind zonenfrei. Ein Messwert
> verschiebt sich **nie**. Die Zone entscheidet allein, in welchen Tages- und Stundentopf er
> fällt (`datetime.fromtimestamp(start_ts)`, `ha_statistics_service.py:946`; 177 solcher
> prozesslokalen Zugriffe in 77 Produktivdateien, **0** davon auf Modulebene).
>
> **Der geltende Vertrag lautet „eedc folgt HA", und das ist Absicht.** Ein harter Pin würde ihn
> umkehren: Wer HA bewusst auf eine Nicht-CET-Zone stellt, sähe eedc und das HA-Energiedashboard
> dann mit **verschiedenen Tagesgrenzen** — heute stimmen sie überein —, und der Checker oben
> würde dauerhaft mit einem Ratschlag warnen, der nichts mehr bewirkt.
>
> **Nicht neu aufrollen.** Weder als harter Pin noch als `setdefault`. Wer es doch will, bringt
> einen **Anwender** mit, den es trifft — nicht das Argument „dann wäre die Zonenfrage weg".
> Dieselbe Bauform wie der `freezegun`-Entscheid darüber: entschieden, begründet, geschlossen.

Die Soll-Zahlen (pytest/Vitest) stehen **nicht hier**, sondern im laufenden Master-Register unter `~/.claude/plans/` — sie ändern sich mit jedem Paket. `check:form-controls` meldet „1 offen (WelcomeStep.tsx)" als dokumentierte Baseline.

**`check:park-leertest` läuft am AUSLÖSER, nicht am Takt** (Entscheid Gernot 23.08.). Er ist ein Playwright-Livetest gegen eine laufende Box und verlangt ein `VITE_DEMO_DEFAULT=true`-Build (Runbook: `~/.claude/plans/runbook-dev-box.md`); seit dem 14.08. grün und keine Baseline mehr.

**Die Regel (verschärft am 24.08., Entscheid Gernot):** Er läuft, wenn das Paket ein **Park-Element hinzufügt** — eine **hinzugefügte** Zeile unter `eedc/frontend/src`, die `data-park-id=`, `<FokusKachel` oder `<Parkbar` enthält, **ohne** Testdateien und **ohne** Kommentarzeilen (Einzeiler oben im Gate-Block; Basis ist `HEAD`, nicht `origin/main`) — **und vor jedem Release**. Sonst nicht, und das braucht dann auch keine Begründung mehr.

> **Warum die zweite Fassung fiel — gemessen 24.08.** Die alte Regel fragte, ob eine geänderte Datei einen Park-Bezeichner **enthält**. Über die letzten **40 Commits** hätte sie **fünfmal** ausgelöst: **zweimal auf reine Testdateien** (`src/test/check-parkbar*.test.ts`, `CockpitJahrV4.test.tsx` — eine Testdatei kann das Laufzeitverhalten des Parks nicht brechen), dreimal auf Produktivdateien, die eine Park-ID nur *enthalten*. **In keinem einzigen der fünf Fälle kam ein Park-Element dazu.** Der teuerste Einzelprüfer des Projekts lief also fünfmal für nichts. Die neue Regel feuert über **150 Commits fünfmal**, alle zwischen dem 15. und 20.08. und alle auf echter Park-Arbeit. Gernots Begründung, die das trägt: *„wenn sie einmal eine entsprechende ID haben und einmal geprüft wurde, ob der Block nicht mehr angezeigt wird, wenn alle der ihm zugeordneten Elemente geparkt sind"* — eine bestehende, unveränderte Park-ID ist bereits geprüft.

> **Warum die alte Fassung fiel:** Sie machte ihn zur Pflicht mit Begründungszwang („wer ihn nicht fährt, sagt das ausdrücklich"). Das ist bei **jedem** Commit eine Ermessensfrage — und mit **188 s der teuerste Einzelprüfer** überhaupt, teurer als ein kompletter pytest-Lauf (gemessen 23.08.). Sein eigener Docstring nennt ihn ausdrücklich „**Kein CI-Pflichtlauf — Dev-Box-Kommando**"; die Regel war strenger als der Prüfer sich selbst versteht. Der Auslöser ist mechanisch entscheidbar statt Ermessen. ⚠ **Die damalige Gegenprobe war halb falsch, gemessen 24.08.:** sie nannte `ef19173d` als Positivbeispiel („meldet fahren"). Dieser Commit fügt **null** Park-Zeilen hinzu, nicht einmal eine im Kommentar — er berührt nur eine Datei, die eine Park-ID *enthält*. **Ein Positivbeispiel, das selbst eine Falschauslösung war**, hat die Regel achtzehn Tage lang bestätigt. Beidseitige Gegenprobe zur heutigen Fassung: `0327416c` (Park-Fix) meldet **5** hinzugefügte Park-Zeilen ⇒ fahren, `e53af679` (nur Testdateien) und `ef19173d` melden **0** ⇒ nicht nötig.
>
> ⚠ **Was er als EINZIGER fängt, bleibt damit gedeckt:** `check:parkbar` (Atomarität) und `check:parkbar-vollstaendig` (Vollständigkeit) sehen nur den **Quelltext**. Drei Klassen entstehen erst zur Laufzeit — Block ohne Auto-Hide-Gate · statische Park-ID-Liste driftet von den real gerenderten IDs · leere Container-Hülle (`FokusKachel`), die sich nicht selbst versteckt. **Dafür gibt es keinen Ersatz.** Wer die Auslöser-Liste kürzt, streicht diese Deckung mit.

**`check:chart-audit`** (35 s) braucht dieselbe Box. Er ist an kein Auslöser-Muster gebunden — wer ihn nicht fährt, sagt das ausdrücklich.

> **Warum die DRITTE Fassung fiel — gemessen 02.09., ausgelöst durch Gernots Frage.** Ich hatte
> den Treffer des Einzeilers mit einer Begründung abgetan (*„die Park-ID ist unverändert"*) — also
> per **Ermessen**, genau dem, was diese Regel seit der ersten Fassung abschaffen soll. Seine
> Rückfrage: *„Willst du dem nicht nachgehen?"*
>
> **Der Befund lag am Prüfer, nicht am Paket.** Die Regel sagt seit dem 24.08. „das HINZUFÜGEN
> zählt"; der Einzeiler zählte Park-Bezeichner in **hinzugefügten Diff-Zeilen** — und eine
> *geänderte* Zeile ist im Diff eine hinzugefügte. Ein Paket, das an einer bestehenden
> `<Parkbar id="chart:wp-vergleich">` nur ein Prop der Kind-Komponente ergänzt, meldete „fahren",
> obwohl die Park-ID-Menge der Datei **bitgleich** blieb (fünf IDs vorher, dieselben fünf nachher).
>
> ⭐ **Dritte Runde derselben Klasse, jedes Mal eine Ebene tiefer:** 1. Fassung *Pflicht mit
> Begründungszwang* (Ermessen bei jedem Commit) → 2. *„Datei **enthält** einen Bezeichner"* → 3.
> *„geänderte **Zeile** enthält einen"* → jetzt *die **Menge** der Park-Elemente wächst*. Die
> Gegenprobe der 3. Fassung hat es nicht gefangen, weil unter ihren drei Beispielen keine geänderte
> Zeile mit bestehender Park-ID war — **eine Gegenprobe prüft nur die Fälle, die sie kennt.**
>
> **Gemessen, beidseitig:** Über die letzten **150 Commits** löst die alte Fassung **dreimal** aus —
> **alle drei falsch, null echte** (`3efc19c5`, `f2c5b747`, `530996f5`; alle dieselbe Bauform, ein
> Prop an einer bestehenden `<Parkbar>`). An den **drei historischen Belegfällen** liefert das neue
> Skript **exakt dieselben** Werte wie die alte Regel — `0327416c` **5**, `e53af679` **0**,
> `ef19173d` **0** —, es verliert also keine Deckung und diskriminiert nur schärfer.
>
> ⛔ **Und was es NICHT ist** (Gernots Rückfrage beim Bau): keine Regel „jedes Element muss parkbar
> sein". Der Auslöser entscheidet, **wann geprüft** wird, nie was erlaubt ist. `<FokusKachel` ohne
> Park-ID zählt mit, weil sie als Container-Hülle genau die Klasse trägt, die **nur** der Leertest
> fängt — sieben davon stehen im Baum und sind alle richtig. Gegenüber der alten Fassung ist das
> sogar **milder**: sie zählte jedes Vorkommen, das Skript verlangt einen **Zuwachs**.

> ✅ **Seit 27.08. verweigern BEIDE Laufzeit-Gates die falsche Box** (geteilter Vorflug, `scripts/demo-box-vorflug.mjs`): fehlt der Demo-Schalter oder ist die Box nicht erreichbar, brechen sie mit Exit 1 ab statt grün zu melden. Vorher meldete `chart-audit` gegen ein Bundle **ohne** `VITE_DEMO_DEFAULT` **37 statt 44 Charts — und Exit 0**. ⚠ **Exit-Codes nie durch eine Pipe messen**: `| tail` liefert den Exit-Code von `tail`, und genau so entstand die Fehlmessung, die diesen Bau ausgelöst hat.

> ⚠ **Hier stand bis 2026-08-14: „danach zwingend `git checkout -- eedc/frontend/dist/` — `dist/` ist versioniert."** **Das gilt nicht mehr** (Fund **N-246**, ausgeliefert mit v4.0.15): `eedc/frontend/dist` ist **nicht mehr versioniert**, weil beide Dockerfiles das Frontend in einer eigenen Stage bauen. Der Schutz gegen einen eingecheckten Demo-Build sitzt jetzt in `release.sh::pruefe_nichts_uebrig`. Ein sauberer Baum heißt seither wirklich sauber — nicht „sauber bis auf `dist/`".

### Release-Workflow (ein Script für alles!)

```bash
cd /home/gernot/claude/eedc-homeassistant
./scripts/release.sh <version>   # Zielversion, z. B. die nächste Patch-Nummer laut CHANGELOG
```

Das Script macht automatisch:
1. Bumpt Version in allen 5 Dateien
2. Kopiert CHANGELOG nach eedc/
3. Committed + taggt + pusht eedc-homeassistant
4. Synchronisiert backend/ + frontend/ nach eedc-Standalone
5. Committed + taggt + pusht eedc

> ⚠ **Einmal beobachtet am 2026-09-02, KEIN Fund (Entscheid Gernot) — aber beim nächsten Lauf
> gezielt nachsehen.** Bei v4.0.38 brach `release.sh` in Schritt 4 ab: `git push origin "vX"`
> meldete `cannot lock ref … reference already exists`, obwohl der Tag im selben Lauf erst
> angelegt worden war. Wegen `set -euo pipefail` endete das Script dort und übersprang damit
> **Schritt 5–7** — den Standalone-Sync **und** `warte-auf-image.sh`, also ausgerechnet die
> Prüfung, die den fehlenden Build gemeldet hätte. Folge: Code und Tag waren draußen, der
> **Release-Workflow lief nie** (er hört auf `push: tags: 'v*'`, und ein Push-Event für den Tag
> gab es nicht) ⇒ kein Image, kein GitHub-Release; die HA-App fand nichts.
>
> **Behoben durch:** Tag remote löschen und identisch neu pushen (`git push --delete origin vX`
> dann `git push origin vX`) — das erzeugt das Event, der Workflow läuft. Schritt 5–6 lassen sich
> aus `release.sh` (Zeilen 314–404) als Wiederaufnahme-Skript nachfahren.
>
> ⛔ **Ursache ungeklärt und NICHT geraten:** `push.followTags` ist nicht gesetzt, es gibt keine
> Hooks und keine Push-Refspec, und im **eedc-Repo lief derselbe Scriptcode sauber**
> (`* [new tag]`). Eine Parallel-Session scheidet aus — deren Tag-Push hätte den Workflow
> ausgelöst. GitHub-Status am selben Tag geprüft: kein Incident.
>
> ⚑ **Deshalb ist es kein Fund:** ein Einzelfall ohne reproduzierbare Ursache. **Tritt es beim
> nächsten Release WIEDER auf, ist es die zweite Runde und wird ein Fund** — dann trägt die
> Beobachtung, und der Fix ist ohnehin ursachenunabhängig: ein abgebrochener Tag-Push darf nicht
> dazu führen, dass die Image-Prüfung entfällt.
>
> ⚠ **Und ein Prüfer-Hinweis aus demselben Vorgang:** Ein `curl` gegen die GHCR-Manifest-API
> **ohne `Accept`-Header antwortet 404**, auch wenn das Image existiert. Wer so misst, meldet
> ein fehlendes Image, das da ist — am 02.09. genau so passiert. Immer mit
> `Accept: application/vnd.oci.image.index.v1+json,…` und **immer mit Positivkontrolle gegen die
> Vorgängerversion**.

**Versionsdateien (5 Stück, alle in eedc/):**

| Datei | Zweck |
| --- | --- |
| `backend/core/config.py` | APP_VERSION (Backend) |
| `frontend/src/config/version.ts` | APP_VERSION (Frontend) |
| `config.yaml` | HA Add-on Version |
| `run.sh` | Startup-Banner |
| `Dockerfile` | `io.hass.version` Label |

> **WICHTIG:** HA Add-ons lesen `eedc/CHANGELOG.md`. Das Release-Script kopiert automatisch.

### Website (Astro Starlight)

```bash
cd website && npm run dev    # http://localhost:4321/eedc-homeassistant/
cd website && npm run build  # Synct automatisch docs/ → website/ (prebuild: website/scripts/sync-docs.sh)
```

**Technik:** Astro Starlight (v0.37), GitHub Pages, German-only
**Deployment:** Automatisch via `.github/workflows/deploy-website.yml` bei Push auf `main`
**Single Source of Truth:** Dokumentationen in `docs/` pflegen, `website/scripts/sync-docs.sh` (npm-`prebuild`, läuft **im `website/`-Verzeichnis**) generiert Website-Versionen mit Frontmatter.

**Starlight-Hinweis:** Invertierte Farbskala im Light Mode! `--sl-color-white` = Text, `--sl-color-black` = Hintergrund. Grau-Skala in `custom.css` definieren.

## Architektur-Prinzipien

1. **Standalone-First:** Keine HA-Abhängigkeit für Kernfunktionen
2. **Datenquellen getrennt:** `Monatsdaten` = Zählerwerte, `InvestitionMonatsdaten` = Komponenten-Details
3. **Legacy-Felder NICHT verwenden:** `Monatsdaten.batterie_*` und das computed-Trio (`eigenverbrauch_kwh`, `direktverbrauch_kwh`, `gesamtverbrauch_kwh`) → erst `InvestitionMonatsdaten`, Legacy nur als expliziter Fallback
4. **`Monatsdaten.pv_erzeugung_kwh` ist KEIN Legacy-Feld, aber auch keine Lesequelle** (Gernot 2026-07-29, ADR-002/**P7**): manuelles bzw. importiertes Anlagen-Aggregat und **ausschließlich Eingang** von `resolve_pv_je_modul` — geladen über `services/pv_monatswerte.py`, nie direkt verrechnet. Einzelwerte und ihre Summe haben immer Vorrang; das Aggregat füllt nur die Lücken der Module **ohne** eigenen Wert. Programmatisch füllen bleibt verboten. Der baumweite Wächter ist `test_wurzelmuster_konformitaet.py::test_p7_*` (Baseline 0). Detail: [BERECHNUNGEN §1](docs/BERECHNUNGEN.md), [ADR-002](docs/ADR-002-WURZELMUSTER.md)
5. **Die Monatszeile wird genau einmal aufbereitet** (ADR-002/**P10**): `services/monats_fakten.py` löst auf, filtert (`aktiv` · Anschaffung · Stilllegung · Dienstwagen) und **ruft** die Layer-Formeln — keine Read-Site faltet `InvestitionMonatsdaten` mehr selbst. Verallgemeinerung von P7 von einer Größe auf die ganze Zeile; Auslöser war die Drift-Inventur 2026-07-31 (sechs Befunde, **kein** Rechenfehler im Layer). **Seit S5 baumweit gewächtert** (`test_wurzelmuster_konformitaet.py::test_p10_*`, funktions-granular, Baseline 0); **der Bauplan ist mit S6 abgearbeitet**, und mit **C1d** (04.08.) steht `P10_NOCH_NICHT_MIGRIERT` auf **0** — **die anlagenweite Restschuld ist getilgt**, der Test hält die Liste jetzt leer statt sie zu deckeln. Detail: [KONZEPT-MONATS-FAKTEN](docs/KONZEPT-MONATS-FAKTEN.md), [ARCHITEKTUR §7](docs/ARCHITEKTUR.md)

## Drei SoT-Regime — nicht mischen

| Dokument | Regelt | Maschinelles Gegenstück |
| --- | --- | --- |
| [`docs/KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (Regel 0/0a) | **Darstellung** — Farben, Komponenten, Typografie, Chart-Konventionen | die `check:*`-Skripte im Frontend (`eedc/frontend/scripts/check-*.mjs`) |
| [`docs/ADR-001-BERECHNUNGS-LAYER.md`](docs/ADR-001-BERECHNUNGS-LAYER.md) | **Schichtung** — *wo* eine Aggregat-Formel definiert wird (`core/berechnungen/`) | `backend/tests/test_berechnungs_layer_konformitaet.py` |
| [`docs/ADR-002-WURZELMUSTER.md`](docs/ADR-002-WURZELMUSTER.md) | **Invarianten** — *was* ein Wert behaupten darf und woher er kommen muss (P1–P10) | `backend/tests/test_wurzelmuster_*.py` |

> **Backend-Wächter sind pytest, keine `check:*`-Skripte** — alle `check:*` sind Frontend-Node-Skripte. **Zwei** Ausnahmen mit eigener Begründung, beide bewachen die Client-Hälfte einer Backend-Regel: `check:kennwert-roh` für ADR-002/P3-a und `check:co2-roh` für ADR-001/DI-2 (der Client konstruiert keine CO₂-Menge; `CO2_FAKTOR_KG_KWH` darf nur noch *angezeigt* werden).
>
> ADR-002 trägt die Pflicht-Spalte **„gesichert durch"** mit der Unterscheidung **Wächter** (baumweit, fängt auch eine Stelle, die es heute noch nicht gibt) und **Regression** (schützt nur die namentlich aufgerufenen Stellen). Wer die Spalte fortschreibt, trägt die Art der Deckung mit ein — eine Regel ohne Code-Beleg gilt als nicht gesichert.

## Design-Konventionen (Regel 0a — Pflicht bei allem Neuen)

> SoT: [`docs/KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (Regel Nr. 0 + 0a am Anfang). Farb-SoT: `frontend/src/lib/colors.ts`.

Bei **allem mit Darstellung** (Seite, Komponente, Chart, Tabelle, Tooltip, Button, Badge, Bericht, Text, Sensor-Name …) gilt: (1) **Regel/SoT existiert → anwenden** (keine lokale/harte Formatierung daneben); (2) **keine, aber sinnvoll → Regel definieren + Zentrale erweitern in derselben Arbeit**; (3) **echter Einzelfall → Maintainer-Freigabe + Code-Kommentar + Ausnahmen-Liste**.

- **Keine Inline-Hex-Farben** außerhalb `lib/colors.ts`. **Pflicht-Check bei Frontend-Arbeit:** `cd eedc/frontend && npm run check:design` (muss 0 melden) — Allowlist-Eintrag = bewusste Freigabe.
- **Eine Datenrolle = eine Farbe** (`lib/colors.ts`); **eine Komponenten-Klasse = eine SoT-Komponente** (KPICard, Button, ChartTooltip, Modal …) — nie eine zweite Komponente für ein bestehendes Pattern.
- **Typ-Reihenfolge** immer aus `INVESTITION_TYP_ORDER`/`compareTyp` bzw. Backend `sort_investitionen_nach_typ`. **Datums-Listen/Tabellen** Default absteigend (neueste zuerst). **% mit Leerzeichen**, **„eedc"** klein.

## Kritische Code-Patterns

### Monatswerte nur aus den Monats-Fakten (ADR-002/P10)

SoT ist `eedc/backend/services/monats_fakten.py`. Wer eine abgeleitete Monatsgröße auswertet, faltet `InvestitionMonatsdaten` **nicht selbst**:

```python
from backend.services.monats_fakten import lade_monats_fakten, finanz_zeile_eingabe

fakten = await lade_monats_fakten(db, anlage_id, von=(2025, 1), bis=(2025, 12))
for f in fakten:                          # RICHTIG — Zeitfilter + Dienstwagen-
    pv    = f.erzeugung.pv_kwh            #   Filter + Auflösung sind schon drin
    bilanz = f.erzeugung.hinter_zaehler_kwh   # EV/Autarkie: inkl. BHKW & Co.
    zeile  = await baue_finanz_zeile(db, anlage_id, finanz_zeile_eingabe(f), ...)

# FALSCH — die Klasse hinter allen sechs Befunden der Inventur 2026-07-31:
for imd in await db.execute(select(InvestitionMonatsdaten)...):
    summe += (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0)
```

Ausgenommen sind **Schreib-, Import- und Checker-Pfade**. Der baumweite Wächter ist **seit S5 scharf** (`test_wurzelmuster_konformitaet.py::test_p10_*`) — **funktions-granular**, damit eine ausgenommene Datei nicht als Ganzes freigestellt ist, mit drei getrennt klassifizierten Ausnahme-Kategorien (`SCHREIBEN_IMPORT_CHECKER` · `PER_INVESTITION` · `NOCH_NICHT_MIGRIERT`, letztere mit Obergrenze im Test). **Umgehängt seit S2:** Aussichten, Jahresbericht-PDF, Investitions-ROI; **S3** Cockpit/CO₂ + Social; **S4** Cockpit/Übersicht + HA-Export; **S5** Komponenten-Dashboards, dazu die PR-Pfade der Aussichten und Prognose-vs-IST; **S6** Community-Payload — damit ist der Bauplan abgearbeitet. **Teil-migriert** — Monatsgrößen ja, per-Investition-Aggregate nein: `aussichten.py`, `ha_export.py`, `investitionen/crud.py`, `dashboards.py`. **C1a** (03.08.) hat `monatsdaten.py::list_monatsdaten_aggregiert` umgehängt — *Auswertungen → Tabelle* und *Cockpit → Jahr*; **C1b** (03.08.) `cockpit/komponenten.py::get_komponenten_zeitreihe` — *Auswertungen → Komponenten*; **C1c** (03.08.) den DB-Zweig von `aktueller_monat.py` — *Cockpit → Monat* (`_collect_saved_data` + `_load_vorjahr` + Sonstige-Positionen; die Präzedenz der vier Quellen bleibt in der Route). **C1d** (04.08.) hat den letzten Posten getilgt — den **Komponenten-Detailblock** von `aktueller_monat.py::get_aktueller_monat` (N-107). **Die anlagenweite Restschuld ist damit 0**, und der Wächter hält die Liste leer statt sie zu deckeln: `test_wurzelmuster_konformitaet.py` führt `P10_NOCH_NICHT_MIGRIERT` ohne Eintrag und prüft `len(...) == 0` (`:2010`). *Hier stand bis 2026-08-22 „Noch anlagenweit selbst faltend (offene Schuld, 1)“ — eine Doku-Zeile gegen einen scharfen Test, gefunden bei der Fundregister-Inventur.*

### SQLAlchemy JSON-Felder

```python
from sqlalchemy.orm.attributes import flag_modified
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")  # Ohne das wird die Änderung NICHT persistiert!
db.commit()
```

### 0-Werte prüfen

```python
# FALSCH: if val:     → 0 wird als False gewertet
# RICHTIG: if val is not None:
```

### Investitions-Kennwerte nur über den SoT-Helper (ADR-002/P3-a)

SoT ist `eedc/backend/core/investition_kennwerte.py`:

```python
from backend.core.investition_kennwerte import get_erzeuger_kwp, get_pv_kwp, get_bkw_kwp

kwp = get_erzeuger_kwp(inv)          # RICHTIG — Typ-Dispatcher (BKW vs. PV-Modul)
kwp = inv.leistung_kwp               # FALSCH — Spalte allein, die #229-Klasse
kwp = getattr(inv, "leistung_kwp")   # FALSCH — der Wächter erfasst auch diese Form
```

Die Nennleistung liegt je nach Herkunft in der **Spalte** `Investition.leistung_kwp` **oder** im `parameter`-JSON. Beide Formen sind gewächtert (`test_wurzelmuster_konformitaet.py::test_p3a_*`, Baseline 0 mit klassifizierten Ausnahmen); im Frontend hält `npm run check:kennwert-roh` dieselbe Trennlinie (**Anzeige/Rechnung** lesen `leistung_kwp_effektiv` aus der Response, **Formulare/Wizards** die Rohspalte). Der `getattr`-Zweig ist nicht optional — über ihn fiel `co2_amortisation.py` durch jede Erhebung.

> `Investition.leistung_kwp` ist ein **Mehrzweckfeld**: beim Speicher trägt dieselbe Spalte kWh, beim Wechselrichter kW (AC). Die Helper gelten nur für Erzeuger-Typen; der Aufrufer filtert.

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| `Monatsdaten.pv_erzeugung_kwh` programmatisch gefüllt **oder direkt gelesen** | Nur manuell/Import; Pro-Modul-Werte nach `InvestitionMonatsdaten`. Lesen ausschließlich über `lade_pv_je_monat`/`pv_summe_je_monat` (P7, s. Prinzip 4) — direkt gelesen ist es entweder eine Teilsumme oder es überschreibt Messungen |
| ROI-Werte unterschiedlich | Cockpit = Jahres-%, Aussichten = Kumuliert-% |
| Zwei Sichten nennen verschiedene CO₂-Zahlen | `berechne_co2_bilanz` ist die **einzige** Konstruktions-Stelle (ADR-001/DI-2: Eigenverbrauch × Strommix **+ WP + E-Mob**), ausgeliefert über `/cockpit/nachhaltigkeit`. Der Client rechnet nichts — Wächter `npm run check:co2-roh`. Der **Tages**-Wert trägt bewusst nur `co2_pv_kg` (WP-Wärme/E-Mob-km gibt es nur monatlich) ⇒ Σ Tage ≠ Monat |
| Erwarteter Monatsbereich beginnt zu früh (fordert Monate vor der Anlage) | **Zwei Datums-Ebenen, zwei Fragen** — nie tauschen: *Zählt diese Investition in diesem Monat?* → `aktiv`/`anschaffungsdatum`/`stilllegungsdatum` **der Investition** (`ist_aktiv_im_zeitraum`). *Welcher Monat soll erfasst sein?* → `Anlage.installationsdatum`, Fallback ältestes Anschaffungsdatum der **Erzeuger** (`core/monats_luecken.py`, Spiegel `lib/monatsLuecken.ts`). `Anlage.installationsdatum` filtert **keine** Auswertung; `Investition` hat gar kein `installationsdatum` (zwei Abstürze). Detail: [ARCHITEKTUR §4](docs/ARCHITEKTUR.md) |
| Nennleistung ist plötzlich 0 | Bei Import-/Altbestand (#229) steht die kWp **nur im `parameter`-JSON** (`kwp` / `leistung_kwp`) — die Spalte allein zu lesen liefert dort still 0. `get_erzeuger_kwp` statt `inv.leistung_kwp` |

## Community-Datenfluss

```
eedc Add-on                                   Community Server
┌───────────────────────────────┐             ┌────────────────────────┐
│ v4/CommunityShareBlock.tsx    │ ─ POST ───→ │ /api/submit            │
│   (teilen / rückw. entfernen) │ ─ DELETE ─→ │ /api/submit/{hash}     │
│ v4/CommunityV4.tsx +          │ ─ Proxy ──→ │ /api/benchmark/        │
│   pages/community/*Teile.tsx  │             │   anlage/{hash}        │
│ "Im Browser öffnen"           │ ─ Link ───→ │ /?anlage=HASH          │
└───────────────────────────────┘             └────────────────────────┘
```

> Der Client spricht den Community-Server **nie direkt** an — alles läuft über `backend/api/routes/community.py` (Proxy + Aufbereitung).

> **Beachte:** Änderungen am Datenmodell müssen in **beiden** Repositories synchron angepasst werden:
> Schemas in `eedc-community/backend/schemas.py` und Aufbereitung in `eedc/backend/services/community_service.py`.
>
> **Der Server rechnet nichts nach** — er hat die Rohdaten nie gesehen. Die Monatswerte kommen seit S6 aus den Monats-Fakten (ADR-002/**P10**), und was ein Feld *bedeutet*, steht als Vertrag im Docstring von `MonatswertInput` (Community-Repo). Wer die Bedeutung ändert, ändert sie dort mit; eine Nachrechnung serverseitig gibt es nicht, Altbestand heilt beim nächsten Voll-Submit.

## Deprecated (nicht löschen!)

> Die alten `ha_sensor_*` Felder im Anlage-Model dürfen NICHT aus der DB/dem Model entfernt werden (bestehende Installationen). Neuer Code nutzt ausschließlich `sensor_mapping`.

## Letzte Änderungen

> **Versions-SoT = [CHANGELOG.md](CHANGELOG.md)** (vollständig, pro Release gepflegt). Dieser Digest ist eine kuratierte Auswahl und kann der Spitze hinterherhinken — `release.sh` bumpt ihn NICHT. Bei Diskrepanz gilt CHANGELOG/`config.py`. **Stand des Digests: v4.0.5** (fortgeschrieben 2026-07-31).

**v4.0.5** (2026-07-31) — Preise je Monat, CO₂ auf dem Eigenverbrauch, eine Zahl je Kennwert:

- **Ein Tarif-Wert trägt den Stichtag seines Monats (ADR-002/P8, gewächtert, Baseline 0):** sechzehn Fundstellen rechneten die Vergangenheit mit dem *heutigen* Tarif — eine Preiserhöhung schrieb die Historie um. Betroffen waren u. a. WP-/Speicher-Dashboard, Monatsbericht, Aussichten-Historie, HA-Export und `GET /monatsdaten/{id}` (dessen handgebaute Query zusätzlich `gueltig_bis` und den `verwendung`-Filter verlor). Dazu: Flex-Ø erreicht die Tagespfade (Σ Tage ≠ Monat war die Folge), „Gültig ab" wird beim ersten Tarif mit dem Inbetriebnahme-Datum vorbelegt, Daten-Checker meldet Monate ohne Tarif-Abdeckung. Auslöser Forum #89667/60 (Algie).
- **Vier Finanz-Sichten, eine Zahl:** USt auf Eigenverbrauch fehlte in PDF, HA-Sensor und den *bisherigen* Aussichten-Erträgen (→ ROI-Fortschritt); der **BKW-Eigenverbrauch** zählte je nach Sicht doppelt, gar nicht oder nur im ROI-Pfad → neuer SoT `core/berechnungen/bkw_finanz.py` (**ADR-002/P9**, Baseline 0). Symmetrie-Test `test_netto_ertrag_vier_wege_symmetrie.py` deckt beide Achsen.
- **Dienstwagen kostet, statt zu verdienen:** PV-Ladung wurde als eingesparter Netzbezug gutgeschrieben und nur die entgangene Einspeisung abgezogen — netto +22 ct/kWh für Strom, den das Haus nie verbraucht hat (196 € > 168 € ohne Auto). Neue Layer-Formel `dienstliche_ladekosten.py` für Cockpit · Aussichten · HA-Export (152 €); Komponenten-Hub zieht nach. **Energiebilanz unberührt.**
- **Eine CO₂-Definition (DI-2 vollendet):** Monatstabelle (Client) und Tagestabelle (Backend) rechneten weiter `Erzeugung × 0,38` — inkl. Einspeisung, ohne WP/E-Mob. Auswertungen → CO₂ liest jetzt `/cockpit/nachhaltigkeit`; Tages-Spalte heißt „CO₂-Einsparung (PV)" (Σ Tage ≠ Monat by design). Wächter `check:co2-roh`. Neu: Block **„CO₂-Bilanz"** in Cockpit → Jahr.
- **BKW-Akku hat einen Erfassungsweg statt zwei:** Kanon = eigene `speicher`-Investition mit BKW-Parent (Live, SoC, Energiefluss, Zählerpfad). Die BKW-eigenen Monatsfelder bleiben erfassbar (`nur_manuell`), aber nicht mehr zuordenbar; Parent-Regel-SoT `models/investition.py::ERLAUBTE_PARENT_TYPEN`, Setup-Wizard bietet den Parent erstmals an. MQTT-Fix: `eigenverbrauch_kwh` lag auf dem Erzeugungs-Kanal.
- **Monats-Fakten-Schicht (ADR-002/P10) ausgeliefert** — S1–S6, Wächter scharf, Restschuld 4. Sichtbare Folgen: Aussichten/PDF/ROI/Prognose-vs-IST/Langfrist/CO₂-Zeitreihe finden die PV bei Gesamtwert-Pflege wieder, HA-Sensoren tragen stillgelegte Komponenten, Community-Payload rechnet mit V2H/BHKW und ohne Dienstwagen. **Social-Media-Textvorlage zurückgebaut** (seit v4.0.0 unerreichbar; Community-Teilen unberührt).

**v4.0.2–v4.0.4** (2026-07-28/30) — Speicher rechnet mit der nutzbaren Kapazität · zugeordnete Sensoren wirken überall (#353 coolxmad) · Daten-Checker erklärt leere Sichten und stellt den Reparatur-Knopf daneben · Balkonkraftwerk in der Prognose (#347, Wechselrichter-Grenze stundenweise) · PV je String bleibt gemessen (Rest-Verteilung statt Alles-Verteilung).

**v4.0.1** (2026-07-26) — Prognose-Werte vereinheitlicht + gemessene PV-Modulwerte:

- **Ein Prognose-Kanon für alle Sichten:** 14-Tage-Balken, Stundenwerte, Kacheln „Morgen/Summe/Ø" und die OM-roh-Kurve rechnen jetzt **jede Ausrichtung getrennt** und mit der gelernten eedc-Korrektur — wie Prognosen-Vergleich und HA-Sensoren. Vorher standen für denselben Tag zwei Zahlen auf einer Seite (Rainer). Bei Mehrfach-Ausrichtung ändern sich die Werte sichtbar; GTI in der 14-Tage-Tabelle ist jetzt **kWp-gewichtet** („GTI Modulfläche").
- **PV-Modulwerte gemessen statt gerechnet:** der Hub-Block „Verlauf" zeigt die Pro-String-Messwerte; wo nur ein Gesamt-Sensor existiert, wird nach kWp verteilt **und gekennzeichnet** („geschätzt (kWp-Anteil)"), statt 0 anzuzeigen. Kein bester/schwächster String, solange verteilt wird.
- **PVGIS: überall die *aktive* Prognose** (P5) — inkl. DB-Invariante gegen „mehrere aktiv" nach Backup-Restore; Monatsbericht-SOLL war dort verdoppelt.
- **Unvollständige Antworten sagen es** (P4): Teil-Fan-out der Wetterabrufe wird ausgewiesen statt still zu niedrig geliefert.
- **Intern:** neue [ADR-002](docs/ADR-002-WURZELMUSTER.md) (sechs Invarianten P1–P6 + Wächter), Anschaffungsdatum ist Pflichtfeld.

**v4.0.0** (2026-07-25) — **IA-V4-Flip: die neue Oberfläche ist ausgeliefert** (Breaking Change, nur UI — Daten unberührt, alte Links werden umgeleitet):

- **Cockpit** (Wann? Live · Tag · Monat · Jahr · Aussicht) · **Komponenten** (Was? je Gerätetyp Status → Verlauf → Vergleich → Wirtschaftlichkeit) · **Auswertungen** (Wie? Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle) · Einstellungen als Kachel-Übersicht. Blöcke sind verschiebbar, fokussierbar (⤢) und parkbar.
- **Monatsabschluss als ein Formular** (statt 7-Schritt-Wizard) · **Datenquellen als eine Fläche** (ein Feld = eine Quelle: HA-Sensor · MQTT · Connector; löst Sensor-Mapping- und MQTT-Wizard ab).
- **Drift-Inventur Tier-1 (DI/DI-2):** WP-CO₂, HA-Export-CO₂, Dienstwagen-Filter, §14a-WP-Tarif, Vorjahres-Nettoertrag — sichtbare Zahlenkorrekturen inkl. einmaligem LTS-Sprung beim CO₂-Sensor. Historische Tarife im PDF/HA-Export (#326).
- Der Rückweg bei Problemen ist v3.45.9; ein separates v3.46 gibt es bewusst nicht.

**v3.45.6–v3.45.9** (2026-06-27/29) — Prognose-Kanon „heute" · Speicher-Vorzeichen-Historie als Daten-Checker-Selbstkorrektur (**keine** Start-Migration) · Hotfix Add-on-Startschleife.

**v3.45.5** (2026-06-22) — Live-Tagesverlauf: Nadel-Spikes bei grobem Energie-Zähler weg (#680). Kurve rekonstruiert Leistung aus kWh-Zähler (`ΔkWh×12000`, 5-Min-Annahme); meldet der Zähler seltener, landet der ganze Zuwachs in EINEM Slot → 13-kW-Nadel. Fix: nur die **Kurvenform** fällt stundenweise auf den Live-Leistungssensor zurück (Phantom-Null-Detektor), Stunden-Energie = Zählersumme bleibt LTS-treu (Σ normiert). Intern (damals hinter `VITE_IA_V4` dormant, **ausgeliefert mit v4.0.0**): **IA-V4 A.3 Cockpit/Live** (IST-Layout in v4-Shell, kein Neubau; durchgängig Fokus/Vollbild via geteiltem `FokusVollbild`/`FokusKachel`, BlockShell auf dasselbe Overlay umgestellt) + Komponenten-Hub-Korrekturen.

**v3.45.4** (2026-06-22) — Sonstige Erzeuger (BHKW) in der Energiebilanz: ein Erzeuger unter „Sonstiges" (Kategorie *Erzeuger*) speist hinter den EINEN Hauszähler → seine Erzeugung zählt jetzt in EV/Autarkie in **allen** Bilanz-Pfaden (Monat + Vorjahr, Live, Tag/Energieprofil) via Layer-SoT `erzeugung_hinter_zaehler_kwh`. PV-Kennzahlen (spez. Ertrag/PR) bleiben rein; CO₂/Wirtschaftlichkeit eines Brennstoff-Erzeugers bewusst „nicht bewertet". Lehre: Bilanz-Drift saß in drei getrennten Pfaden — Symptom-Patch hätte nur den Monat erwischt.

> **v3.30–v3.44:** Detail nur noch im [CHANGELOG](CHANGELOG.md) (Digest hier seit v3.29.2 nicht fortgeschrieben).

**v3.29.x** (2026-05-13/14) — Aggregations-Hardening + UX-Bündel vor Menüstruktur-Konzept:

- **Anschaffungs-/Stilllegungsdatum-Filter durchgängig (v3.29.0/v3.29.1, #236 #239):** alle Read-Sites (Cockpit, Energieprofil, HA-Stats-Aggregation, Monatsbericht-Sektionen) respektieren jetzt `inv.installationsdatum`/`stilllegungsdatum`. Folgewelle nach #236 zeigte: Filter auf einer Schicht reicht nicht bei parallelen Pfaden.
- **SoT-Helper `get_inv_value` für `leistung_kwp` (#229):** PV-String-Verteilung liest jetzt Spalten-Wert mit Fallback auf `parameter`-JSON statt Gleichverteilung.
- **UX-Cluster #233 (P13–P18):** chirurgische Fixes Display-Token `'—'`, kWh-Einheiten im WP-Dashboard (#237), Daten-Checker Inbetriebnahme-Monat ausgeschlossen (#240), Sparkline-Tooltip mit Monatsname (#241).
- **eedc-Schreibweise (v3.29.2):** ~130 Treffer in Code + Hilfe-Docs auf Wort „eedc" vereinheitlicht; `\bEEDC\b`-Wortgrenze schützt Identifier wie `EEDC_Prognose` automatisch.

**v3.28.0** (2026-05-13) — Reparatur-Werkbank: Mehrere Tage neu aggregieren (#230).

**v3.27.x** (2026-05-10/12) — Etappe 3d + Tester-Päckchen:

- **Etappe 3d Daten-Provenance & Reparatur-Werkbank (v3.27.0):** Anomalie-Erkennung mit punktuellem Reparatur-Pfad; bewusst KEIN globaler Heiler-Knopf.
- **UX-Sprint A1+A2+A3 + Power-Sensor-Bug (v3.27.1, #200):** Wizard + Live-Heute + Stats-API ziehen jetzt `_is_energy_sensor` konsistent durch (kW darf nicht in kWh-Slot).
- **WP-Aggregation: Split-Strommessung + Counter-Spike-Cap (v3.27.4, #230):** MartyBr-Bug-Report mit Screenshot als Vorlage.
- **UX-Cluster detLAN (v3.27.5, #207 #215 #217 #218 #494) + Folge-Päckchen Tester-Bugs (v3.27.3, #220 #222 #226 #227 #228).**

**v3.26.x** (2026-05-06/09) — Korrekturprofil + HA-Energy-Import + Etappe 3c:

- **EEDC-Korrekturprofil O1+O2 (v3.26.0–v3.26.2):** Päckchen 1 (Recency) + Päckchen 2 (Sonnenstand × Wetter live) parallel zum Legacy-Skalar als Diagnose. Live-Pfad-Switch wird in Prognosequellen-Wahl Schritt 2 mitgemacht.
- **HA-Energiekonfiguration importieren (v3.26.5, #197):** Setup-Vereinfachung Olli0103 — Energy-Dashboard-Konfig aus HA wird im Setup-Wizard übernommen.
- **Etappe 3c Energieprofil Read-/Write-Architektur konsolidiert (v3.26.8):** zentraler SoT-Helper statt Drift-Patches; siehe `docs/archive/KONZEPT-DATENPIPELINE.md`.
- **Reload-Vorschau Counter-Boundary + „Nur neu rechnen" (v3.26.6):** Vorschau heilt sich selbst.

**v3.25.x** (2026-04-29/05-05) — Live-Snapshot 5-Min + Investitions-Parameter-SoT:

- **Live-Snapshot 5-Min Backend (v3.25.3–v3.25.6):** Phase 1 Backend für Live-Tagesverlauf-Service ausgeliefert + validiert (Off-by-one-Fix state→sum). Frontend-Umstellung noch offen.
- **Investitions-Parameter Single Source of Truth (v3.25.0):** `lib/investitionParameter.ts` + `core/investition_parameter.py` als gemeinsame Konstanten-Map; DB-Migration `_migrate_investitionen_parameter_keys_v325` korrigiert 7 Drift-Bugs (V2H, Jahresfahrleistung, PV-Ladeanteil, Vergleichsverbrauch, Speicher-Arbitrage, Wallbox-Leistung, WP-Preis-Default).
- **Pool-Bug Quick-Fix Wallbox+E-Auto (v3.25.11):** Drift-Konsistenz zwischen `cockpit/uebersicht.py` und `aktueller_monat._aggregate` angeglichen.

**v3.24.x** (2026-04-27/29) — WP-Kompressor-Starts + In-App-Hilfe + Sensor-LTS:

- **WP-Kompressor-Starts (v3.24.0, #136):** optionaler Total-Increasing-Sensor pro WP, neue `KUMULATIVE_COUNTER_FELDER`-Architektur trennt Counter strikt von kWh-Feldern. KPI-Kacheln in Monatsbericht + WP-Dashboard (v3.24.4, #169).
- **Sensor-Filter aufgeweicht + „ohne Statistik"-Badge (v3.24.1, #136 Folge):** Nibe-Roh-Counter ohne `state_class` jetzt auswählbar, Frontend-Fallback-Link, Daten-Checker-Kategorie SENSOR_MAPPING_LTS — siehe `feedback_ha_lts_keine_zeitmaschine.md`.
- **In-App-Hilfe als pflegbares Werk (v3.24.2):** Sweep aller acht Hilfe-Dokumente (BENUTZERHANDBUCH, HANDBUCH_INSTALLATION/BEDIENUNG/EINSTELLUNGEN/INFOTHEK, BERECHNUNGEN, SENSOR-REFERENZ, GLOSSAR) auf v3.24-Stand. Sidebar-Eintrag „Was ist neu" (v3.24.5, Discussion #130 Folge Safi105).
- **PV-Cockpit: Speicher-Kapazität + WR-Eigenleistung sichtbar (v3.24.4/v3.24.6, #172 detLAN):** Key-Drift `batteriekapazitaet_kwh` vs. `kapazitaet_kwh` korrigiert, Orphan-Speicher-Block ergänzt.

**v3.23.x** (2026-04-25/27) — MAE/MBE + MQTT-Daten-Checker + Mobile-Hardening:

- **MAE + Bias trennen im Genauigkeits-Tracking (v3.22.0/v3.23.x, #151):** drei Quellen (OpenMeteo/EEDC/Solcast), Bias neutral gefärbt, Spaltenstruktur stabil auch ohne Lernfaktor.
- **MQTT-Topic-Abdeckung im Daten-Checker (v3.23.7, #134):** Drift zwischen dynamischer Konsumenten-Seite und statischer Publisher-Seite wird sichtbar; bei nicht aktivem Subscriber stillschweigend übersprungen (v3.23.8 detLAN/rapahl).
- **Klickbarer Reparatur-Popover bei IST-Lücke (v3.23.0, #147):** Button „Tag neu berechnen" + Fallback-Link Sensor-Mapping. Restart-Recovery für verpasste :05/:55-Snapshot-Jobs.
- **iOS Safari `h-dvh` + COP→JAZ-Harmonisierung (v3.23.6/v3.23.4, #161/#167):** siehe `feedback_ios_companion_app.md` und Wizard-Sweep für Key-Drift (`batterie_kwh`→`batteriekapazitaet_kwh` u. a.).

**v3.19.0–v3.22.0** (2026-04-22/25) — Architekturwechsel + Slot-Konvention + WP-Gaspreis:

- **kWh aus Zähler-Snapshots statt Leistungs-Integration (v3.19.0, #135):** kritischer Architekturwechsel — stündliche `sensor_snapshots`-Tabelle, Self-Healing, ±5–15 % Drift weg.
- **Performance Ratio nutzt GTI statt GHI (v3.20.0, #139):** physikalisch unmögliche PR-Werte >1.2 im Winter korrigiert.
- **Slot-Konvention auf Backward vereinheitlicht (v3.20.0, #144):** OpenMeteo/Solcast/IST jetzt alle Slot N = Energie [N-1, N), Industriestandard.
- **WP-Alternativvergleich + Monats-Gaspreis (v3.21.0, #141) + aufklappbare Energieprofil-Sektionen (#148).**

**v3.17.0–v3.18.0** (2026-04-21) — Dynamische Benzinpreise + Energieprofil-Tab:

- **Dynamische Benzinpreise aus EU Weekly Oil Bulletin (v3.17.0):** echte monatliche Kraftstoffpreise statt statischem Parameter, History seit 2005.
- **Energieprofil-Tab + anlage-spezifische Datenverwaltung (v3.18.0, #133):** Tages-Tabelle mit Spalten-Selektor, Pro-Tag-Reaggregation, Vollbackfill aus HA-Statistik.

**v3.16.x** (April 2026) — Solcast PV Forecast (v3.16.4): Prognosen-Vergleich-Tab (OpenMeteo / EEDC kalibriert / Solcast / IST); Sensor-Mapping Strompreis (Tibber/aWATTar/EPEX), Stündliche Strompreis-Mitschrift; Infothek Etappe 3.6 (v3.16.2).

**Ältere Meilensteine:** PDF-Dokumente + Infothek N:M (v3.15), Stilllegungsdatum (v3.14), Monatsberichte + Energieprofil Etappe 3 (v3.12/3.13), Import-Strategie (v3.10), Live Dashboard Generalüberholung (v3.9), L2-Cache (v3.7), Infothek (v3.5), Wettermodell-Kaskade (v3.4), GTI-Prognose (v3.3), Live Dashboard + MQTT-Inbound (v3.0).

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Roadmap & offene Punkte

Single Source of Truth: **GitHub Issue [#110 — Roadmap Anfrage](https://github.com/supernova1963/eedc-homeassistant/issues/110)**.

Aktuellen Stand bei Bedarf abrufen via `gh issue view 110 --repo supernova1963/eedc-homeassistant`.
