# KONZEPT — Ladezeit Aussicht/Live: Cache-Befund + SWR-Entwurf (R18-13 / R18-2 vertieft)

> ## **Status (gemessen 2026-08-08): umgesetzt · eine Maßnahme bewusst offen · drei verworfen**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** **`hooks/useApiData.ts` (Zeile 17) und `useApiData.test.tsx` nennen dieses Dokument wörtlich als SoT** — bis heute zeigte dieser Verweis ins Gitignore und war für jeden Mitleser ein 404.
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen:** nur **LZ-4** (SWR-Opt-in für drei V3-geteilte VM-Hooks) — *bewusst*, weil der gemessene Nutzen dort gering ist. **LZ-5 ist verworfen und wird nicht neu evaluiert** (die Messwerte geben einen L3-Payload-Cache nicht her).
>
> ⚑ **Der Merksatz unten ist der eigentliche Wert dieses Dokuments:** die Wartezeit war zu rund 95 % ein absichtlicher `sleep()`, nicht Rechenlast. Wer *zu langsam* hört, misst zuerst.


## Maßnahmen-Register (fortschreibbar — Stand 2026-07-28)

> Dieses Dokument bleibt liegen, weil es der **SoT für `hooks/useApiData.ts`** ist (`useApiData.ts:17`
> + `useApiData.test.tsx:6` zitieren es) und weil Memory `reference_ladezeit_prognose_unvermeidbar`
> auf es als revidierte Wahrheit zeigt.

| # | Maßnahme | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **LZ-1** | **Jitter raus aus dem User-Pfad** (`skip_jitter=True`, 3 Stellen) | ✅ 2026-07-11 | gemessen: `solar-prognose` **28,7 s → 0,26 s**, `tagesprognose` **18,6 s → 0,17 s** |
| **LZ-2** | **SWR als Erweiterung der Fetch-SoT** (`swrKey`/`keepPreviousData`, kein neuer Hook — Regel 0a) | ✅ | Playwright: jeder Wiederbesuch **ohne Skeleton**; ohne Option Verhalten unverändert ⇒ V3 unberührt |
| **LZ-3** | Skeleton-Label sichtbar (400 ms-Delay, Platz reserviert) | ✅ | `BlockStackSkeleton`, bei 2,5 s künstlicher Latenz belegt |
| **LZ-4** | **SWR-Opt-in für `usePrognoseVsIst` / `usePvStrings` / `usePrognoseVergleich`** | ⬜ **bewusst offen** | V3-geteilte VM-Hooks mit Backfill-Aktionen; Sektions-Skeletons warm ~100 ms ⇒ geringer Nutzen. Nach demselben Opt-in-Muster nachziehbar. **Heimat ist dieses Dokument** — bewusst kein Roadmap-Punkt, weil der gemessene Nutzen gering ist |
| **LZ-5** | L3-Payload-Cache | ⛔ **verworfen** — die Messwerte geben ihn nicht her (warm 8–180 ms) | nicht neu evaluieren |
| **LZ-6** | P4 Guest-Box-Prefetch | ⛔ obsolet (durch LZ-1 erledigt) | — |
| **LZ-7** | `CommunityV4` auf SWR | ⛔ bewusst nicht — Dispatcher-Muster erfüllt den Zweck | — |
| **LZ-8** | ⚠ **Eine Aussage über die ABWESENHEIT von Daten bekommt keinen `swrKey`** | ✅ 2026-08-17 (N-270) | `v4/HubLeerGrund.tsx` hatte einen (Begründung: „nicht den Grund des vorigen Geräts stehen lassen") — und der Cache bewirkte genau das Gegenteil: Wer den Knopf drückte, Monatswerte erfasste und in *Komponenten* zurückkam (Tab-Wechsel = Remount), sah für eine API-Runde „noch keine Monatswerte erfasst" **über den nun gefüllten Blöcken**. Ein stale Messwert ist eine alte Zahl; eine stale *Abwesenheits-Aussage* ist eine **falsche** Aussage. Der Abwägung fehlt hier auch die Gegenseite: es gibt kein Skeleton zu vermeiden, die Komponente rendert bis zur Antwort `null`. ⚠ **Abgrenzung, gemessen:** `v4/TagLeerGrund.tsx` behält seinen Key — es wird nur aus dem bereits leeren Zustand heraus gerendert, zeigt immer mindestens seinen Text, und sein Key trägt das Datum. Baumweiter Sweep über alle 13 `swrKey`-Verwender: **die Klasse hat genau ein Mitglied** (die übrigen `return null` hängen an „noch nichts geladen" oder einer lokalen Bedingung, keine ist eine server-gelieferte Abwesenheits-Aussage). Probe: `v4/HubLeerGrund.test.tsx` (Remount-Zusicherung auf den **ersten** Paint) |

**Merksatz aus der Diagnose:** die Wartezeit war zu ~95 % ein absichtlicher `sleep()`
(`random.uniform(1, 30)` Jitter gegen Lastspitzen), **nicht** Rechenlast. Wer das nächste Mal
„zu langsam" hört: erst messen, wo die Zeit hingeht — die naheliegende Erklärung war falsch.

---

> **Status: ✅ P1–P3 UMGESETZT 2026-07-11** (gleiche Session, Gernot-Go nach der Diagnose;
> committed auf `main`, mit v4.0.0 ausgeliefert).
>
> **Verifiziert (Messwerte nach Umsetzung):**
> - **P1** (`skip_jitter=True` in `solar_prognose.py` ×2, `energie_profil/views.py:1102`,
>   `live_wetter.py:1262`): Kalt-Messung wiederholt — `solar-prognose` **28,7 s → 0,26 s**,
>   `tagesprognose` **18,6 s → 0,17 s** (L1+L2 leer, Scheduler aus, r27-DB).
> - **P2** (R18-2 SWR): NICHT als neuer Hook, sondern Regel-0a-konform als **Erweiterung
>   der bestehenden Fetch-SoT `hooks/useApiData.ts`** (Optionen `swrKey` +
>   `keepPreviousData` + `swrCachePeek/Store` für Poll-Sichten; ohne Option Verhalten
>   unverändert → V3 unberührt). Umgestellt: CockpitAussicht/Monat/Tag/Jahr/Live (Live nur
>   Erst-Paint-Seed, Poll unverändert), Auswertungen-Basis (`useAuswertungBasis` →
>   `useAggregierteDaten` Opt-in), ROI (`useRoiAnalyse` Opt-in `swrKeyBasis`), CO₂-Amort,
>   Finanzen-Sonderkosten + T-Konto, Tabelle (`useWerteZeitreihe`/`useTagesWerte`).
>   Playwright-Nachweis: **jeder Wiederbesuch KEIN Skeleton** (Aussicht 2./3./4. Besuch,
>   Monat/Jahr 2. Besuch, Finanzen/Tabelle 2. Besuch); Erst-Besuche ehrlich 180–440 ms.
>   D7-2/D12-1/D7-6-In-Place-Verhalten (Monats-/Tages-/Modus-Wechsel) via
>   `keepPreviousData` erhalten.
> - **P3** (R18-13): `BlockStackSkeleton`-Label sichtbar (400 ms-Delay, Platz reserviert,
>   sr-only-Parität). Playwright-Nachweis bei 2,5 s künstlicher API-Latenz: Label nach
>   ~2,4 s sichtbar, opacity 1.
> - **Gates:** 366/366 Vitest grün · tsc sauber · `check:design` 0 · ESLint-Delta 0 (98→98)
>   · de-de-Wächter 0 (2 dokumentierte `de-de-allow` für Cache-Keys).
>
> **Bewusster Rest (nicht umgesetzt):** `usePrognoseVsIst`/`usePvStrings`/
> `usePrognoseVergleich` (AuswertungenPrognoseV4-Sektionen) — komplexe V3-geteilte
> VM-Hooks mit Backfill-Aktionen; ihre Sektions-Skeletons sind warm ~100 ms. Bei Bedarf
> nach demselben Opt-in-Muster nachziehen. CommunityV4 bleibt beim Dispatcher-Muster
> (erfüllt den Zweck). P4 (Guest-Box-Prefetch) wie vorhergesagt obsolet.
>
> Ursprünglicher Auftrag: Diagnose + Konzept (Ausgangspunkt `TRIAGE-TESTER-IA-V4-20260624.md`
> → R18-13, rapahl #213/#216/#218: „dauert zu lange", „nach längerer Wartezeit wieder
> langsam", „in jedem Block werden die Daten neu aktualisiert"; detlan #215 sieht es lokal
> nie). Der Diagnose-Teil unten ist unverändert der Stand VOR der Umsetzung.

## TL;DR

**Die Wartezeit ist NICHT rechenintensiv — sie ist zu ~95 % ein absichtlicher `sleep()`.**
Bei Cache-Miss schläft der Open-Meteo-Abruf `random.uniform(1, 30)` Sekunden
(Jitter gegen Lastspitzen, `services/wetter/cache.py:28` + `solar_forecast_service.py:267-268`)
— **auch im interaktiven User-Request-Pfad**. Bei der Multi-String-Demo-Anlage
(4 Ausrichtungen, parallel gefeuert) wartet der User auf das **Maximum von 4
Jitter-Würfen ≈ 25 s im Erwartungswert**. Gemessen: Erst-Load Aussicht kalt **26,6 s**,
warm **1,4 s**; die eigentliche Aggregation kostet warm **8–180 ms**.

Auf der Guest-Box tritt das stündlich wieder auf, weil `EEDC_DISABLE_SCHEDULER=true`
**auch den 45-Min-Prefetch abschaltet** → nach 60 Min TTL ist der Cache kalt, und der
nächste Besucher zahlt den vollen Jitter. detlan (lokal, Scheduler an → Prefetch alle
45 Min innerhalb der 60-Min-TTL) hat **nie** einen kalten Cache — deshalb sieht er nichts.

Konsequenzen: (1) **Jitter raus aus dem User-Pfad** (3 Stellen, `skip_jitter=True` —
`prognosen.py` macht es längst überall vor) → kalt fällt von ~26 s auf ~2 s.
(2) **Frontend-SWR** (R18-2 vertieft, ohne React Query) → Tab-Wechsel zeigen alte Daten
statt Skeleton. (3) **Kein L3-Payload-Cache nötig** — die Zahlen geben ihn nicht her.
(4) Memory `reference_ladezeit_prognose_unvermeidbar` ist zu **revidieren**.

---

## 1. Messwerte (A) — Methode + Ergebnisse

### Methode (reproduzierbar)

- **Backend:** lokale Box, `EEDC_DISABLE_SCHEDULER=true` (= Guest-Box-Konfiguration),
  DB = **Kopie von `eedc/data/devbox-r27-demo.db`** (die Guest-Demo-DB, Multi-String-Anlage
  mit 4 Ausrichtungen), Start:
  `EEDC_DISABLE_SCHEDULER=true DATABASE_URL="sqlite+aiosqlite:///<kopie>.db" backend/venv/bin/uvicorn backend.main:app --port 8099`
- **Kalt** = frischer Prozess (L1 leer) + `DELETE FROM api_cache` (L2 leer) vor dem Start.
  **Warm** = unmittelbar wiederholter Request (L1-Hit). Echte Open-Meteo-Calls (kein Mock).
- **Timing:** `curl -w '%{time_total}'` je Endpoint; UI-Messung per Playwright/Chromium
  gegen Vite-Dev (`VITE_IA_V4=true`, :3000 → Proxy :8099): Zeit bis Aussicht-Blöcke
  sichtbar + API-Call-Zählung je Tab-Wechsel (`page.on('request')`).
- Warm-Werte sind über 3 Runden stabil (±10 ms); Kalt-Werte streuen mit dem
  Zufalls-Jitter (1–30 s je Wurf) — zweimal gemessen (25,1 s / 28,7 s solar-prognose).

### Backend-Endpoints kalt vs. warm (r27-Demo-DB)

| Endpoint (Sicht) | kalt | warm | Anteil kalt |
| --- | ---: | ---: | --- |
| `/api/solar-prognose/1?tage=14` (Aussicht kurz) | **28,7 s** | 0,011 s | Jitter (max von 4 parallelen Würfen); reine API-Zeit ~1,5 s |
| `/api/energie-profil/1/tagesprognose?datum=+1` (Stunden-Block) | **18,6 s** | 0,028 s | eigener Jitter-Wurf (eigener Cache-Key) |
| `/api/aussichten/prognosen/1` (eedc-Heute-Wert) | 0,42 s | 0,013 s | kein Jitter (`skip_jitter=True` durchgängig) |
| `/api/aussichten/finanzen/1?monate=12` | 0,12 s | 0,08–0,18 s | reine DB/CPU, kein externer Call |
| `/api/aussichten/langfristig/1?monate=12` (Aussicht lang) | 0,011 s | 0,008 s | reine DB/CPU |
| `/api/aussichten/trend/1?jahre=5` | 0,011 s | 0,008 s | reine DB/CPU |
| `/api/live/1/wetter` (Live/Wetter heute) | **0,18 s** | 0,011 s | Open-Meteo-Call OHNE Jitter → so schnell ist „kalt" ohne Sleep! |
| `/api/live/1` | 0,003 s | 0,003 s | — |
| `/api/live/1/tagesverlauf` | 0,004 s | 0,003 s | — |

**Aufschlüsselung der Wall-Clock (Auftrag A a–d):**

- **(a) Externe Quell-API:** Ein Open-Meteo-Roundtrip kostet **~0,2–0,5 s**
  (Beleg: `live-wetter` kalt 0,18 s — derselbe API-Typ, nur ohne Jitter).
  Der Rest der 18–29 s ist der **Jitter-Sleep**, kein Netzwerk.
- **(b) Aggregation/Berechnung im Endpoint:** warm ≤ 0,18 s über alle Sichten
  (solar-prognose 11 ms, langfristig 8 ms, finanzen ~0,1 s). Auch die pro-Stunde-
  Korrekturfaktor-Lookups im Live-Wetter (Schleife `live_wetter.py:1145 ff.`) kosten
  gesamt ~11 ms. **„Aussicht ist echt rechenintensiv" (Triage) ist damit widerlegt.**
- **(c) DB-Zeit:** in (b) enthalten, SQLite-indiziert, unauffällig.
- **(d) Frontend-Render:** 0,2–0,3 s je Sicht-Mount (Skeleton-Flash warm, s. u.).

### UI-Messung (Playwright, Vite-Dev :3000)

| Szenario | Ergebnis |
| --- | --- |
| Erst-Load Aussicht, **kalt** | **Skeleton steht ~26,6 s** (solar-prognose 25,6 s, tagesprognose 11,2 s — parallel; das Maximum gewinnt). = Rainers #213-Bild 1:1 |
| Erst-Load Aussicht, warm | Inhalt nach ~1,4–1,6 s |
| Tab-Wechsel → Monat (warm) | Skeleton ~0,2 s, **6 API-Calls** |
| Tab-Wechsel → Aussicht, 2./3. Besuch (warm) | Skeleton 0,3–0,8 s, **8 API-Calls — jedes Mal, voller Refetch** |

Rainers „**in jedem Block werden die Daten aktualisiert**" (#218) ist damit gemessen
bestätigt: jeder Sub-Sicht-Besuch = unmount → remount → kompletter Refetch → Skeleton
(= R18-2). Bei warmem Cache nur ein Flackern; bei kaltem Cache steht das Skeleton
bis zu ~30 s nackt (R18-13).

### Warum Rainer es sieht und detlan nie (Umgebungs-Mechanik)

1. Guest-Box läuft mit `EEDC_DISABLE_SCHEDULER=true` (statische Demo, `deploy-guest.sh`).
2. Damit entfallen ALLE drei Prefetch-Pfade (`main.py:176` Sofort-Prefetch,
   `main.py:344` Initial-Prefetch, `scheduler.py:217-219` 45-Min-Job) — der Cache
   wird NUR durch User-Requests gefüllt.
3. Quell-TTL = 60 Min (`FORECAST_CACHE_TTL`). Nach > 60 Min Leerlauf: Cache kalt.
4. Erster Besucher danach zahlt Jitter (bis 30 s) + API. → „Nach längerer Wartezeit
   dauert es wieder länger" (#216) ist exakt dieses Muster, **kein** Proxmox-/
   Co-Tenant-Kaltstart (der trägt allenfalls Sekundenbruchteile bei).
5. detlan lokal: Scheduler an → Prefetch alle 45 Min < TTL 60 Min → nie kalt.

Der L2-Cache (SQLite) mildert nur **Neustarts** (Warmup L2→L1), nicht **Leerlauf** —
nach TTL-Ablauf ist L2 genauso abgelaufen wie L1.

---

## 2. Befund (B) — L2-Abdeckung, Jitter, Payload-Cache

### Fakten-Gegenprüfung (Auftragsliste)

| # | Behauptung | Ergebnis |
| --- | --- | --- |
| 1 | L2 cacht nur Quellen, nicht Sicht-Payloads | ✅ bestätigt (`wetter/cache.py`; Services cachen Roh-API-Antworten je Koordinaten/Parameter-Key) |
| 2 | Kein SWR im Frontend, Refetch je Tab-Wechsel | ✅ bestätigt + **gemessen** (8 Calls je Aussicht-Besuch) |
| 3 | CommunityV4 lädt einmal im Dispatcher | ✅ bestätigt (`v4/CommunityV4.tsx:77-87` → Props an 6 Sub-Tabs) |
| 4 | Skeleton-Label nur sr-only | ✅ bestätigt (`BlockStackSkeleton.tsx:37-38`) |
| 5 | Triage: „Aussicht echt rechenintensiv" | ❌ **widerlegt** — warm ≤ 0,18 s; die Zeit ist Jitter-Sleep |

### Der eigentliche Fehler: Jitter im interaktiven Pfad

`fetch_gti_forecast` schläft bei Cache-Miss `random.uniform(1, 30)` s
(`solar_forecast_service.py:267-268`). Gedacht ist das als Lastverteilung für
**Hintergrund**-Abrufe vieler Installationen gegen Open-Meteo — der Prefetch hat dafür
aber längst seinen EIGENEN Jitter (einmal pro Durchlauf, `prefetch_service.py:51-52`)
und ruft die Services mit `skip_jitter=True` auf. Ein interaktiver Klick ist keine
Thundering-Herd; `api/routes/prognosen.py` (Prognosen-Vergleich) setzt deshalb schon
heute **durchgängig `skip_jitter=True`** (Z. 394–522). Drei Pfade sind übrig geblieben:

| Stelle | Pfad | Wirkung |
| --- | --- | --- |
| `api/routes/solar_prognose.py:252/297` | `get_multi_string_prognose`/`get_solar_prognose` ohne `skip_jitter` | Aussicht kurz: bis 30 s (Multi-String: max mehrerer Würfe) |
| `api/routes/energie_profil/views.py:1102` | `get_solar_prognose` ohne `skip_jitter` | Stunden-/Tagesprognose: bis 30 s |
| `api/routes/live_wetter.py:1262` | `kanon_tagesprognose(..., skip_jitter=False)` | Live-Solar-Aussicht-Kanon: bis 30 s bei Miss |

**Empfehlung P1:** an diesen drei Stellen `skip_jitter=True` (User-Request = interaktiv).
Open-Meteo-Schutz bleibt: Prefetch-Jitter + Negative-Cache + 60-Min-TTL unverändert.
Erwartete Wirkung (gemessen ableitbar): Erst-Load Aussicht kalt **~26,6 s → ~2 s**.

### Deckt der L2-Cache ab, was er soll? Lücken?

**Ja — die Abdeckung ist richtig geschnitten.** Gecacht wird die teure, externe Quelle
(Open-Meteo/Solcast/BrightSky/PVGIS/Strompreis) je Koordinaten+Parameter; die
anlagen-spezifische Veredelung (kWp-Skalierung, Korrekturprofil, KPI-Bau) läuft je
Request neu — und kostet gemessen 8–180 ms. Das ist kein Leck, sondern korrekte
Arbeitsteilung. Auch Anlagen-Parameter-Änderungen (Neigung, kWp, Korrekturprofil)
wirken so sofort, ohne Invalidierungslogik.

**Rechnet der Aussicht-Endpoint bei warmem L2 jedes Mal neu?** Ja (`_build_prognose`
je Request) — bei 11 ms Gesamtkosten irrelevant.

### Payload-Cache (L3)? **Nein.**

- Nutzen: maximal ~0,18 s (Finanz-Prognose) — unterhalb der Wahrnehmungsschwelle,
  und genau die Fälle, die das Frontend-SWR (Abschnitt 3) ohnehin unsichtbar macht.
- Kosten: Invalidierungs-Matrix (anlage_id × horizont × Parameter-Änderungen ×
  Korrekturprofil-Updates × Zeitpunkt) + Staleness-Risiko im Live-Pfad („Live darf
  nicht einfrieren") + zweite Cache-Wahrheit neben dem Quell-Cache.
- Regel-Fit: [[feedback_bestehende_mechanik_nutzen_nicht_erfinden]] — das Problem ist
  nicht fehlendes Caching, sondern (1) Jitter im User-Pfad, (2) fehlendes SWR im Client.

**Erweiterbarkeit des bestehenden Cachings:** `_cache_get/_cache_set` (cache.py) ist
bereits ein generischer key→value-TTL-Store mit L2-Persist; sollte je ein
Payload-Cache nötig werden, wäre er dort als Nutzer derselben Mechanik anzusiedeln
(ein Decorator wäre reine Kosmetik). Für DIESES Problem: nichts erweitern.

### Guest-Box-Konfiguration (nachgelagert)

`EEDC_DISABLE_SCHEDULER=true` bleibt für die statische Demo richtig (kein
Tageszeilen-Drift). Nach P1 ist der Kalt-Fall (~2 s) auch ohne Prefetch akzeptabel —
**keine** neue Sonder-Betriebsart bauen ([[feedback_sonderfaelle_nicht_reflexhaft_codieren]]).
Erst falls Gernot ~2 s kalt immer noch zu lang findet, wäre ein separates
„Prefetch-ohne-Persist"-Flag zu diskutieren.

---

## 3. SWR-Entwurf (C) — Community-Muster ohne neue Abhängigkeit

### Ziel

Beim erneuten Besuch einer Sicht (Tab-Wechsel, Horizont-Wechsel) bleiben die **alten
Daten sichtbar**, der Refetch läuft still im Hintergrund (`reloading`), das Skeleton
erscheint NUR wenn es für den Key noch nie Daten gab (echter Erst-Load, Anlagenwechsel).
Kein React Query (Gernot-Entscheid), keine neue Dependency.

### Warum nicht 1:1 das Community-Muster (alles in den Dispatcher heben)?

CommunityV4 funktioniert, weil alle 6 Sub-Tabs **dasselbe eine** Benchmark-Objekt
teilen. Die Cockpit-Zeit-Sichten haben dagegen **disjunkte** Datenmengen (Monat:
4 Endpoints; Aussicht: 4–5 andere; Live: wieder andere, mit Poll-Intervallen). Alles
in `CockpitV4` zu heben hieße: jeder Tab-Besuch lädt ALLE Sichten, der Dispatcher wird
zum Fetch-Monolithen ([[feedback_grosse_dateien_beim_umbau_splitten]] rückwärts).
Das Community-Muster ist der richtige **Effekt** (Daten überleben den Sub-Wechsel),
aber der Halteort muss außerhalb des Komponenten-Baums liegen, nicht im Dispatcher.

### Entwurf: EIN SoT-Hook `useSichtDaten` mit Modul-Cache

Neue Datei `frontend/src/hooks/useSichtDaten.ts` (~60 Zeilen), Verhalten:

```ts
// Modul-Singleton — überlebt unmount/remount, stirbt mit dem Browser-Tab (bewusst:
// nach Browser-Refresh ist ein Erst-Load korrekt und ehrlich).
const sichtCache = new Map<string, unknown>()

export function useSichtDaten<T>(opts: {
  key: string | null            // z. B. `aussicht-kurz:${anlageId}` — null = inaktiv
  laden: () => Promise<T>       // der bestehende Lade-Closure der Sicht (unverändert)
}): {
  daten: T | null               // Cache-Stand sofort, frischer Stand nach Refetch
  loading: boolean              // true NUR wenn kein Cache-Eintrag existiert (Skeleton-Fall)
  reloading: boolean            // true während Hintergrund-Refetch (ReloadButton-Spin)
  error: string | null          // Fehler OHNE Cache = Fehlerzustand; MIT Cache = alte Daten bleiben
  reload: () => void            // manueller Reload (ReloadButton), immer silent
}
```

Semantik (deckt die heutigen Sonderfälle ab):

1. **Mount, Cache-Hit:** `daten` sofort aus der Map, `loading=false`, `reloading=true`,
   `laden()` läuft; Ergebnis ersetzt Map + State. → kein Skeleton, kein Layout-Sprung.
2. **Mount, Cache-Miss:** `loading=true` → `BlockStackSkeleton` wie heute (R18-13-Label).
3. **Key-Wechsel** (Anlage, Horizont): wie Mount — Hit → still, Miss → Skeleton.
   Das ersetzt die handgebaute `geladenFuer`-Ref-Logik (D11-9) in CockpitAussichtV4.
4. **Refetch-Fehler bei vorhandenen Daten:** alte Daten bleiben stehen, `error` gesetzt
   (Sicht kann dezent hinweisen); **ohne** Daten → `FehlerZustand` wie heute.
5. **Race-Schutz:** pro Key nur der letzte Request gewinnt (Zähler/AbortRef wie die
   bestehenden `let ab = false`-Muster).
6. Kein TTL im Client: SWR revalidiert bei JEDEM Mount — maximale Staleness = Dauer
   des laufenden Refetch. Live-Daten frieren nicht ein (Poll-Intervalle der Live-Sicht
   bleiben unberührt).

### Betroffene Dateien (Umbau je Sicht: Fetch-Closure in den Hook stecken)

| Datei | heutige Mechanik → Umbau |
| --- | --- |
| `v4/CockpitAussichtV4.tsx` | `laden()`+`loading`/`reloading`/`geladenFuer` (Z. 139–217) → `useSichtDaten` je Horizont-Key (`aussicht-kurz:${id}` / `aussicht-lang:${id}`); Tagesprognose separat gekeyt (`aussicht-stunden:${id}:${datum}`) |
| `v4/CockpitMonatV4.tsx` | gleicher Umbau, Key `monat:${id}:${monat}` |
| `v4/CockpitTagV4.tsx` / `v4/CockpitJahrV4.tsx` | analog (`tag:…`, `jahr:…`) |
| `v4/CockpitLiveV4.tsx` | nur Erst-Paint über den Hook; Poll-Loop unverändert |
| `v4/AuswertungenFinanzenV4/RoiV4/PrognoseV4/Co2V4/TabelleV4.tsx` | je eigener Key `ausw-<sub>:${id}:…` — Dispatcher `AuswertungenV4.tsx` bleibt dumm (Routing only) |
| `v4/CommunityV4.tsx` | bleibt wie ist (Muster erfüllt den Zweck bereits); optional später auf den Hook |
| `hooks/index.ts` | Export ergänzen |

Regel-0a-Einordnung: neuer Fall „Sicht-Daten-Lebenszyklus" → **eine** neue SoT-Mechanik
(Hook), von allen V4-Sichten geteilt; keine Zweitlösung pro Sicht. UI-Regime unberührt
(kein Style-Thema), Berechnungs-Regime unberührt (reiner Transport, ADR-001-konform).

---

## 4. Antwort auf D — macht SWR die R18-13-Anzeige überflüssig?

**Fast, aber nicht ganz — R18-13 schrumpft auf die Erst-Load-Absicherung, genau wie
in der Triage vermutet:**

- **Navigation/Tab-Wechsel** (Rainers Hauptärgernis): mit C verschwindet das Skeleton
  vollständig — alte Daten stehen, Refetch still. R18-13 hat hier keinen Fall mehr.
- **Echter Erst-Load** (erster Besuch der Sicht pro Browser-Session, Browser-Refresh,
  Anlagenwechsel): Skeleton bleibt — und dafür ist das sichtbare Label (R18-13,
  `BlockStackSkeleton` sichtbar statt sr-only, ~400 ms-Verzögerung) weiterhin richtig
  und billig. Mit P1 (Jitter weg) steht es aber nur noch ~1–3 s statt bis zu 30 s.
- R18-13 also **wie beschlossen bauen** (EINE Zentrale, R18-Bündel) — es ist die
  Absicherung des Restfalls, nicht mehr die Hauptantwort auf die Wartezeit.

## 5. Antwort auf E — Memory `reference_ladezeit_prognose_unvermeidbar`

**Revidieren.** Die Wartezeit ist weder CPU- noch API-gebunden:

- CPU/Aggregation: ≤ 0,18 s (gemessen) — kein Faktor.
- Externe API: ~0,2–0,5 s je Roundtrip — spürbar, aber klein.
- **Dominant: absichtlicher Jitter-Sleep 1–30 s im User-Pfad bei Cache-Miss**
  (entfernbar, P1) + fehlender Prefetch auf der Guest-Box (Scheduler aus) +
  fehlendes Client-SWR (maskierbar, P2).

Unvermeidbar bleibt nur der ~0,5–2-s-Erst-Load bei wirklich kaltem Quell-Cache.
Memory-Update ist vorgemerkt (nach Gernots Kenntnisnahme dieses Dokuments).

## 6. Empfohlene Umsetzung (priorisiert — Vorschlag für Gernots Entscheid)

| Prio | Maßnahme | Dateien | Aufwand | Wirkung |
| --- | --- | --- | --- | --- |
| **P1** | `skip_jitter=True` im interaktiven Pfad (3 Stellen, Präzedenz `prognosen.py`) | `solar_prognose.py:252/297`, `energie_profil/views.py:1102`, `live_wetter.py:1262` | ~1 h inkl. Test | kalt ~26,6 s → ~2 s; wirkt sofort auf Guest-Box, HA-Add-on, Standalone |
| **P2** | SWR-Hook `useSichtDaten` + Umbau Cockpit-/Auswertungen-Sichten (R18-2 vertieft) | neuer Hook + 9 Sicht-Dateien (Tabelle §3) | Hook ~½ Tag; je Sicht 15–30 min → gesamt ~1–1,5 Tage | kein Skeleton mehr bei Navigation; „in jedem Block neu geladen" weg |
| **P3** | R18-13 Label sichtbar (~400 ms Delay) — wie im R18-Bündel beschlossen | `BlockStackSkeleton.tsx` | ~1 h | Rest-Wartezeit (Erst-Load) erklärt statt stumm |
| P4 | Nur falls nach P1 nötig: Guest-Box-Prefetch-Frage (kein neuer Modus ohne Bedarf) | — | — | vermutlich obsolet |

Empfohlene Reihenfolge: **P1 zuerst** (kleinster Eingriff, größter Effekt, entschärft
Rainers Bild unabhängig vom Frontend), dann P2+P3 zusammen im R18-Bündel.
Gegencheck nach P1: Kalt-Messung von §1 auf der Dev-Box wiederholen (Soll: < 3 s).

---

### Anhang: Rohdaten-Herkunft

- Messläufe 2026-07-11, lokale Box; Logs/Skripte im Session-Scratchpad
  (`backend-r27*.log`, `messung-tabwechsel.mjs`, `messung-kalt2.mjs`).
- DB-Kopien in `/tmp` (Scratchpad), Original `data/eedc.db` unangetastet
  (eine vom Mess-Prefetch geschriebene HEUTE-Zeile + 11 api_cache-Einträge
  wurden rückstandsfrei entfernt).
- Jitter-Mathematik: max von n unabhängigen U(1,30)-Würfen; n=4 → E ≈ 24,8 s.
  Gemessen 25,1 s / 25,6 s / 28,7 s — konsistent.
