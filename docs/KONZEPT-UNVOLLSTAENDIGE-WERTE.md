# Regel — was eedc sagt, wenn ein Messwert fehlt

> ## **Status (gemessen 2026-08-29): die Regel gilt, ist gewächtert und liefert ihre Provenance aus**
>
> **Was hier steht:** wie eedc mit einem fehlenden Messwert umgeht — und warum es ihn **nicht**
> durch 0 ersetzt. §3 ist die tragende Regel; **23 Stellen im Code zitieren sie**, dazu
> [BERECHNUNGEN.md](BERECHNUNGEN.md). §6 nennt die Regressionen und den Wächter, die sie halten.
>
> ⭐ **Am 2026-08-29 geschlossen: das Provenance-Flag hat seine Leser.** §2.4 nannte
> `pv_vollstaendig` den schärfsten Einzelbefund der Inventur — gesetzt, getestet, von keiner
> Route gelesen. Es erreicht jetzt die Monatstabelle (je Zeile), Cockpit → Monat und
> Cockpit → Jahr (als `hinweise`, P4-Form), und **Wächter W1** hält den Zustand: ein
> Domänen-Flag ohne Zugriff unter `backend/api/` macht die Suite rot.
>
> **Auslöser:** Rainer (PN 89905), gefunden an coolxmads Screenshot, nicht an der eigenen Anlage:
> fällt ein Sensor aus, verschwindet der **abgeleitete** Wert (Hausverbrauch) ganz, obwohl Netz
> und Batterie weiter messen.
>
> **Sein Lösungsvorschlag „fehlend → 0" wird nicht gebaut.** Er verstößt gegen die 0-Werte-Regel
> (`is not None`, nicht `if val`) und gegen „HA-Werte sind SoT, kein stiller Fallback". Eine 0
> macht aus *unbekannt* ein *war nichts* — der Hausverbrauch stünde dadurch zu hoch, ohne dass es
> jemand sieht. Das ist schlimmer als eine Lücke.
>
> **Verhältnis zu ADR-002/P4:** P4 gilt für die Wetter-/Prognose-Abrufe (zwei Response-Verträge,
> `tests/test_wurzelmuster_p4_teilsumme.py`). Dieses Dokument dehnt dieselbe Regel auf
> **abgeleitete Energiegrößen** aus.
>
> ⚑ **Der Bauplan steht nicht mehr hier.** Paket-Schnitt und Wächter-Vorschlag sind am 2026-08-28
> herausgelöst worden — ein öffentliches Dokument beschreibt den gebauten Zustand, keinen
> Arbeitsvorrat. §2 nennt weiterhin die Stellen, an denen die 0 im Code steht; das ist die
> **Begründung** der Regel und keine Aufgabenliste.

---

## §1 Der Befund

**Beide Verwechslungen kommen vor, und beide sind still.**

| Richtung | Was passiert | Folge |
| --- | --- | --- |
| **unbekannt → 0** | ein fehlender Summand wird als 0 eingesetzt | die Zahl steht da, **sieht gültig aus** und ist falsch |
| **0 → unbekannt** | eine gemessene 0 wird zu `null` | die Anzeige zeigt „—", der Nutzer sucht einen Fehler, den es nicht gibt |

Ein Konzept, das nur eine Richtung regelt, ist halb. Die vier Fälle aus der
v4.0.6-Startmenge belegen beide (N-47 · N-48 → Richtung 1, N-52 → Richtung 2,
89905 → eine dritte Form: **Totalunterdrückung**).

**Die entscheidende Beobachtung der Inventur:** eedc behandelt Lücken heute an
**jeder** Stelle anders, und die Unterschiede sind nirgends als Entscheidung
aufgeschrieben. Am schärfsten sichtbar in **einer einzigen Funktion** —
`services/live_power_service.py::_calc_tages_ev_hv` (`:388-401`) wendet auf vier
Sensoren **drei** verschiedene Regeln an:

```python
if pv is None or einsp is None:
    return None, None                                   # (1) Totalunterdrückung
bat_ladung = sum(v for k, v in kwh.items() if k.endswith("_ladung") and v)   # (2) unbekannt → 0
…
hausverbrauch = … if bezug is not None or eigenverbrauch > 0 else None       # (3) `bezug or 0`
```

Fehlt die PV, verschwindet **auch** der Hausverbrauch, den Netz und Batterie
tragen würden — das ist Rainers Meldung, wörtlich. Fehlt die Batterie, wird sie
still als 0 gerechnet und der Direktverbrauch zu hoch. Fehlt der Netzbezug, wird
der Hausverbrauch **zu niedrig** ausgeliefert, ohne Kennzeichnung. Drei
Fehlerrichtungen, eine Funktion, keine davon dokumentiert.

---

## §2 Inventur

Erhoben per baumweitem Grep über `.py`/`.ts`/`.tsx` ohne Glob-Einschränkung
(ein Fund über eine Lücke braucht den Negativbeweis); Tests, Seed-Skripte und
Doku-Treffer ausgenommen. **Die Startmenge des Auftrags war unvollständig** — vier
Stellen unten (`live_komponenten_builder`, `live_dashboard`, `crud`, `types.ts`)
standen in keinem Register.

### §2.1 Wo die Lücke vernichtet wird (Richtung 1: unbekannt → 0)

| Stelle | Ausprägung |
| --- | --- |
| `core/berechnungen/verbrauch.py:66-71` | **Der Kern.** `berechne_verbrauchs_kennzahlen` nimmt sechs `float` und macht aus jedem `None` per `or 0.0` eine 0. Die **Signatur hat keinen Platz für „unbekannt"** — ab hier ist die Information weg, für alle fünf Aufrufer |
| ~~`services/monats_fakten.py`: `einspeisung_kwh=(monatsdaten.einspeisung_kwh or 0.0) …`~~ | ⛔ **Am 2026-08-29 am Code widerlegt — die Begründung stimmte nicht.** Hier stand „Die NULL-Spalte in `Monatsdaten` **weiß** es; die Schicht wirft es hier weg". Gemessen: `einspeisung_kwh` und `netzbezug_kwh` sind `nullable=False, default=0` — im Modell **und** in drei echten Datenbanken (`NOT NULL`, 0 NULL-Zeilen). Das `or 0.0` kann dort nichts wegwerfen. Was tatsächlich Information verliert, ist der andere Zweig — `if monatsdaten else 0.0`, also ein Monat **ohne Zählerzeile** —, und **den führt die Schicht bereits**: `MetaFakten.hat_zaehlerzeile`, gelesen von acht Stellen unter `backend/api/`. *Eine Inventur-Zeile, die eine Spalte für nullable hält, ohne ins Modell zu sehen* |
| `services/monats_fakten.py:658` | `pv_kwh = (pv_modul_summe or 0.0) + roh.bkw_erzeugung` — **die Schicht bricht ihre eigene, ausgeschriebene Regel** (s. §2.3) |
| `services/monats_fakten.py:513-520` | `kennzahlen_aus_fakten` summiert über Monate; ein Monat ohne Zählerzeile geht als 0 ein |
| `core/calculations.py:157-161` | Legacy-Pfad, gar keine Guards |
| `api/routes/cockpit/uebersicht.py:328` · `ha_export.py:389` · `monatsdaten.py:504` · `core/berechnungen/finanz_aggregat.py:120` | die vier Aufrufer des Kerns — erben dessen Blindheit unverändert |
| `services/pdf/builders/jahresbericht.py:285-296` · `:346-347` | `gesamt = ev + netz` ohne Guard |
| `services/live_power_service.py:395-400` | Batterie- und Netzbezugs-Lücke → 0 (s. §1) |
| `services/live_komponenten_builder.py:356` | `(einspeisung_w or 0)` im Live-Direktverbrauch |
| `api/routes/live_dashboard.py:133` | `eigenverbrauch = pv_kw - einsp_kw` ohne Guard |
| `api/routes/monatsdaten.py:749-751` | **Schreibpfad**, und der einzige, der eine Lücke **persistiert**: `(md.batterie_ladung_kwh or 0)` bzw. `(… entladung … or 0)` landen in der DB. Zwei Einschränkungen, die die Tragweite senken und deshalb hier stehen: der wichtigste Summand **ist** geschützt (`if md.pv_erzeugung_kwh is not None`), und Ziel sind die **Legacy**-Felder des computed-Trios, die neuer Code nicht mehr liest (CLAUDE.md Prinzip 3) |
| `frontend/src/pages/auswertung/types.ts:140-147` | **Der Client hebt die Ehrlichkeit des Backends wieder auf:** vier `\|\| 0` hintereinander, und `md.autarkie_prozent ?? calcAutarkie(…)` rechnet die vom Backend bewusst als `null` gelieferte Quote aus 0-ersetzten Summanden **neu aus** |

### §2.2 Wo eine gemessene Null verschwindet (Richtung 2)

| Stelle | Ausprägung |
| --- | --- |
| ~~`api/routes/prognosen.py`~~ | ✅ **gebaut 2026-08-29 (N-52).** War: `if ist_heute_kwh > 0 else None` — jede gemessene Null (Nacht, Winter, Schnee) wurde zu „—". Träger ist jetzt `StundenProfil.hat_messung`. ⛔ **Nicht** `is not None`, wie es hier zuerst vorgeschlagen war: `ist_profil` liefert `tageswert_kwh` **nie** als `None` (die Summe startet bei 0.0), die Regel wäre immer wahr gewesen und hätte eine Anlage ganz ohne PV-Zähler mit „0,0 kWh IST" beschriftet. *Aus einem zu strengen Prüfer wäre ein falscher Wert geworden* |
| `services/live_verbrauchsprofil_service.py:491` | `max(0.0, v_end - v_start)` macht aus einem Counter-Reset eine gemessene Null (**N-47**) |
| `services/live_verbrauchsprofil_service.py:615` | `tage >= 2` zählt **Tage statt Abdeckung** — ein „Tag" entsteht aus einer einzigen Stunde (**N-48**) |

### §2.3 Wo es bereits richtig gemacht wird — die Referenzformen

Das ist der wichtigste Teil der Inventur: **eedc hat die Muster schon.** Sie sind
nur nicht als Regel aufgeschrieben und deshalb nicht durchgesetzt.

| Stelle | Form |
| --- | --- |
| `api/routes/solar_prognose.py:402-408` | **Der geltende P4-Vertrag.** Wert bleibt stehen, wird beschriftet, **mit Umfang** („nur 3 von 4 Teilanlagen"). Ausdrücklich: „kein Ersatz durch Schätzung, keine Kappung" |
| `services/daten_checker/monatsdaten.py:531-544` | Dreifacher `is not None`-Guard, sonst wird die Prüfung übersprungen — „eine Prüfung, die schlicht nicht prüfbar ist" |
| `api/routes/aktueller_monat.py:1276-1295` | **Gestufte** Unterdrückung: ohne Einspeisung kein Eigenverbrauch; ohne Netzbezug zusätzlich kein Gesamtverbrauch und keine Autarkie — aber der Eigenverbrauch **bleibt**. Die feinste Behandlung im Baum |
| `core/berechnungen/tagesbilanz.py:92-115` | NULL-Stunden zählen nicht als 0; Quoten `None` statt 0, „damit die UI '—' statt '0 %' zeigt" |
| `api/routes/import_export/csv_operations.py:454-461` | Import setzt `eigenverbrauch = None` vor, rechnet nur im Guard |
| `services/monats_fakten.py:116-135` | `ErzeugungFakten.pv_module_kwh: Optional[float]` — im Docstring steht die richtige Regel wörtlich: „Wer summiert, behandelt `None` als Lücke, **nie** als 0" |

### §2.4 Der schärfste Einzelbefund: ein Flag ohne Leser

`monats_fakten.py` **hat** bereits ein Provenance-Flag. Es wird gesetzt
(`:667`), in die Meta-Gruppe gereicht (`:752`) und von zwei Tests geprüft. Der
baumweite Grep, **ohne Glob, über beide Repo-Hälften**:

```
eedc/backend/services/monats_fakten.py:143   pv_vollstaendig: bool = True     ← Definition
eedc/backend/services/monats_fakten.py:341   pv_vollstaendig: bool = True     ← Definition
eedc/backend/services/monats_fakten.py:667   pv_vollstaendig=…                ← gesetzt
eedc/backend/services/monats_fakten.py:752   pv_vollstaendig=…                ← gesetzt
eedc/backend/tests/test_monats_fakten_schicht.py:146,166,167                  ← geprüft
```

**Kein einziger Konsument las es** — keine Route, kein Schema, keine Zeile im
Frontend. Das Flag war vollständig implementiert, getestet und **erreichte die
Antwort nie**.

> ✅ **Behoben am 2026-08-29.** `pv_unvollstaendig_hinweis()` in
> `services/monats_fakten.py` ist die eine Stelle, die aus dem Flag einen Satz
> macht; ausgeliefert wird er als `hinweise` (P4-Form, wie
> `SolarPrognoseResponse`) in **Cockpit → Monat** und **Cockpit → Jahr**, und als
> Feld `pv_vollstaendig` **je Zeile** in `/monatsdaten/aggregiert` — dort ist die
> Zeile der Monat, ein Satz auf Seitenebene verlöre die Zuordnung.
> **Wächter W1** (`backend/tests/test_konformitaet_provenance_flag_hat_leser.py`)
> hält es: ein boolesches `*_vollstaendig`-Feld der Domänen-Schicht ohne
> Attributzugriff unter `backend/api/` macht die Suite rot.

**Wo die Teilsumme wirklich sichtbar wurde — gemessen 2026-08-29, denn die
Fundstellen unterscheiden sich:**

| Sicht | Verhalten VOR dem Bau |
| --- | --- |
| Cockpit → **Jahr** (`cockpit/uebersicht.py`) | `sum(f.erzeugung.pv_kwh …)` **ohne Guard** — die Kopfzahl war still zu niedrig, und daran hängen spezifischer Ertrag und SOLL/IST |
| Monatstabelle (`/monatsdaten/aggregiert`) | zeigte **schon** „—" (`hat_pv_imd` verlangt `pv_module_kwh is not None`) — das Flag ersetzt die Unterdrückung hier nicht, es **erklärt** sie |
| Monatstabelle **mit Balkonkraftwerk** | ⛔ der schlimmste Fall: `hat_pv_imd` wird durch das BKW wahr, die Antwort liefert `pv_erzeugung_kwh` = **nur BKW** und `pv_module_kwh` = **0,0** — eine Zahl, die wie eine Messung aussieht. Gegengerechnet: 500 kWh gemessener String-Ertrag fehlen in beiden Zahlen |

### §2.5 Die Klasse, die keine Registerzeile hatte: Differenzen aus Teilsummen

`core/berechnungen/tagesbilanz.py` überspringt NULL-Stunden korrekt (§2.3) — und
rechnet in `:117` trotzdem:

```python
eigenverbrauch = pv_sum - einspeisung_sum
```

**Zwei Teilsummen mit möglicherweise verschiedener Abdeckung werden voneinander
abgezogen.** Fehlen der Einspeisung sechs Stunden und der PV keine, ist der
Eigenverbrauch zu hoch — um genau die nicht gemessene Einspeisung. Das Feld
`stunden: int` (`:65`) zählt **Rows, nicht Feld-Abdeckung** und kann die Frage
nicht beantworten. Dieselbe Differenz steht in
`api/routes/energie_profil/views.py:590` und `:1400`.

Das ist keine Nachlässigkeit einer Stelle, sondern eine **eigene Fehlerklasse**:
richtige NULL-Behandlung je Summand schützt die Summen, aber nicht die aus ihnen
gebildete Differenz.

> ✅ **Seit 2026-08-22 gebaut (N-92) — dieser Abschnitt beschrieb bis zum
> 29.08. einen Zustand, den es nicht mehr gab.** `TagesBilanz` führt die
> **Abdeckung je Achse in Stunden** (`pv_stunden` · `verbrauch_stunden` ·
> `einspeisung_stunden` · `netzbezug_stunden`) und dazu die beiden
> Paar-Abdeckungen; `eigenverbrauch` und `autarkie` werden **unterdrückt**,
> sobald die Grundlagen auseinanderlaufen. `energie_profil/views.py` trägt
> dieselbe Regel (der frühere Befund `:590`, heute `:997`).
>
> ⚠ Die zweite genannte Stelle (`views.py:1400`, heute `:1830`) gehört **nicht**
> zu dieser Klasse: sie summiert eine **Prognose**, kein Messfeld — dort gibt es
> keine Abdeckungsfrage. Am 29.08. gemessen und abgegrenzt.

---

## §3 Was die ehrliche Anzeige ist — Empfehlung

Der Auftrag stellt drei Kandidaten gegeneinander. **Keiner gewinnt global**, und
das ist keine Ausflucht, sondern folgt aus einer Eigenschaft der Formel:

> **Die Frage ist nicht „Wert oder kein Wert", sondern: kennt man die Richtung
> des Fehlers?**

| Formelform | Teilergebnis ist | Empfehlung |
| --- | --- | --- |
| **additive Summe** (PV über Strings, Σ über Stunden) | **richtungssicher zu niedrig** — nie zu hoch | **beschriften** (Kandidat b) |
| **Differenz** (`PV − Einspeisung − Ladung`) | Richtung **unbestimmt**: fehlt die Einspeisung, zu hoch; fehlt die PV, zu niedrig | **unterdrücken** (Kandidat a) |
| **Quotient** (Autarkie, EV-Quote) | Zähler und Nenner können verschiedene Abdeckung haben | **unterdrücken** |

**Begründung.** Eine beschriftete Teilsumme ist brauchbar, weil der Nutzer weiß,
in welche Richtung er korrigieren muss („mindestens so viel"). Eine beschriftete
**Differenz** ist es nicht: ihre Fehlerrichtung hängt davon ab, *welcher*
Summand fehlt, und diese Information müsste man ohnehin mitliefern — dann kann
man den Wert auch gleich weglassen. Ein Wert, dessen Fehlerrichtung niemand
kennt, ist schlechter als eine Lücke, weil er Vertrauen beansprucht, das er nicht
verdient.

**Das erklärt rückwirkend den bestehenden Baum.** `solar_prognose` ist additiv
und beschriftet (richtig). `aktueller_monat` ist eine Differenz und unterdrückt
(richtig). `berechne_verbrauchs_kennzahlen` ist eine Differenz und unterdrückt
**nicht** (falsch). Die drei haben nie widersprüchlich gehandelt — es fehlte nur
der Satz, der sie zusammenhält.

**Kandidat (c), Unter-/Obergrenze, wird verworfen.** Er bräuchte eine zweite,
unabhängig gemessene Größe als Schranke — die es für den Hausverbrauch nicht
gibt — und verdoppelt jede Kachel. Für den einzigen Fall, in dem eedc eine echte
Schranke hat (PV gegen PVGIS-SOLL), ist das bereits eine Plausibilitätsprüfung im
Daten-Checker und keine Anzeigefrage.

**Ergänzend, gegen Richtung 2:** Unterdrückung wird **nur** an `is not None`
entschieden, nie an `> 0`. Eine gemessene 0 ist eine Aussage und wird als „0"
angezeigt, nicht als „—".

**Zwei Regeln, die aus §2.5 und §2.4 folgen:**

1. **Eine Differenz erbt die Unvollständigkeit jedes Summanden.** Wer aus zwei
   Teilsummen eine Differenz bildet, prüft die Abdeckung **beider**.
2. **Ein Provenance-Flag ohne Leser ist kein Provenance.** Wer eines einführt,
   liefert es im selben Schritt aus.

---

## §4 Verhältnis zum Daten-Checker

Der Auftrag warnt vor „doppelten Meldewegen als neue Drift-Quelle". Die Inventur
zeigt: **die Drift existiert bereits, und zwar in verschärfter Form.** Der Checker
meldet die Fälle heute schon — wörtlich (`daten_checker/monatsdaten.py:306-319`):

- „Einspeisung nicht erfasst" — ERROR, Detail: *„ohne Einspeisung sind
  Eigenverbrauch und Autarkie **nicht berechenbar**"*
- „Netzbezug nicht erfasst" — ERROR, Detail: *„ohne Netzbezug sind Hausverbrauch
  und Stromkosten **nicht berechenbar**"*
- „Batterie-Ladung nicht erfasst (Speicher vorhanden)" — WARNING, Detail: *„Ohne
  Batterie-Daten wird der Hausverbrauch **falsch berechnet**"*

**eedc sagt an einer Stelle „nicht berechenbar" und zeigt zwei Klicks weiter eine
Zahl.** Das Papier führt also keinen zweiten Meldeweg ein — es bringt den
bestehenden mit der Anzeige in Übereinstimmung.

**Zuständigkeitsgrenze (keine Überschneidung):**

| | Daten-Checker | Die Sicht selbst |
| --- | --- | --- |
| **Frage** | „Was musst du nachtragen?" | „Worauf beruht *diese* Zahl?" |
| **Umfang** | anlagenweit, alle Monate | genau der gezeigte Zeitraum |
| **Anlass** | der Nutzer sucht Arbeit | der Nutzer liest eine Zahl |
| **Form** | Befundliste mit Link/Action | Beschriftung am Wert bzw. „—" |

Der Text der Beschriftung wird **nicht** neu erfunden: die Detail-Sätze oben sind
bereits formuliert und geprüft. Sie sind die Quelle für den Hinweis am Wert.

---

## §5 Grenze zum Reparatur-Pfad

Die Grenze ist im Code bereits gezogen und muss nur benannt werden.
`CheckErgebnis` (`daten_checker/kategorien.py:107-119`) trägt **beide** Wege:

| Feld | Wann | Heutige Nutzung |
| --- | --- | --- |
| `link` | der Wert kann **nur vom Menschen** kommen (Zählerstand ablesen, Monatsabschluss pflegen) | die Pflichtfeld-Meldungen aus §4 → `/monatsabschluss/…` |
| `action_kind` | die Maschine kann ihn **aus vorhandenen Rohdaten neu ableiten** | heute genau eine: `reaggregate_day` |

**Die Regel daraus:** Ausweisen ist immer richtig — es ist die Aussage über die
Zahl, nicht das Angebot einer Lösung. Ein **Reparatur-Angebot** kommt nur dazu,
wenn die Rohdaten die Lücke tatsächlich schließen können (Snapshots/LTS
vorhanden, nur die Aggregation fehlt). Fehlt der Messwert selbst, gibt es
**keinen** Knopf, sondern den Link zur Eingabe.

Die Regel gilt unverändert: kein globaler
Heiler-Lauf, der über alle Monate „repariert". Und die HA-LTS-Grenze bleibt —
Home Assistant ist keine Zeitmaschine: was HA nie gespeichert hat, kann eedc
nicht rekonstruieren, und ein Reparatur-Knopf, der das suggeriert, wäre eine
Lüge in Knopfform.

---
## §6 Wächter — was heute prüft

Für die allgemeine Form gibt es bewusst **keinen** Grep-Wächter: `except → return 0` ist im
Connector-/Wetter-Layer die **richtige** Form (rund 40 Stellen) und im Wert-Pfad die falsche —
der Unterschied liegt nicht im Ausdruck. Das steht so schon in ADR-002.

Geprüft wird am Ergebnis — **und seit 2026-08-29 zusätzlich strukturell**, dort wo es geht:

> **W1 — kein Provenance-Flag ohne Weg in die Antwort**
> (`backend/tests/test_konformitaet_provenance_flag_hat_leser.py`, Baseline 0).
> Jedes **boolesche** `*_vollstaendig`/`*_unvollstaendig`-Feld unter `services/`
> oder `core/` braucht einen **Attributzugriff** unter `backend/api/`.
>
> ⛔ **Attributzugriff, nicht Textsuche — am eigenen Prüfer gelernt.** Die erste
> Fassung suchte den Namen als Text und blieb bei der Gegenprobe **grün**,
> obwohl die Auslieferung testweise zurückgebaut war: eine Kommentarzeile nannte
> den Namen, eine **gleichnamige Funktion** an anderer Stelle
> (`pv_monatswerte.ist_vollstaendig`) zählte als Leser eines gleichnamigen
> Response-Feldes, und die TypeScript-Typdeklaration des Clients zählte
> ebenfalls. *Ein Prüfer, der bei zurückgebautem Fix grün bleibt, hat nichts
> gemessen.* Die Gegenprobe steht seither als eigener Test in der Datei.
>
> **Schema-Felder unter `api/` sind nicht Gegenstand** — sie *sind* die Antwort;
> ihr Konsument sitzt im Client. Dafür ist W3 zuständig (Regression je Endpoint).

Dazu die Regressionen am Ergebnis (gemessen 2026-08-29):

- `backend/tests/test_unvollstaendige_werte_b1_b3.py` — **beide Richtungen an einem Ort**:
  eine PV-Teilsumme bleibt stehen und sagt es (Richtung 1), eine gemessene Null bleibt
  eine 0 (Richtung 2). Enthält die Negativprobe gegen `is not None`, die den ursprünglich
  vorgeschlagenen Fix als Regression entlarvt hätte.

- `backend/tests/test_tagesbilanz_pv_nicht_erfasst.py` — eine additive Größe ohne Messung wird
  unterdrückt statt als 0 geführt.
- `backend/tests/test_live_tageswerte_luecken.py` — der Auslöserfall (Rainer): fällt ein Summand
  aus, verschwindet die Differenz, statt zu hoch zu stehen.
- `backend/tests/test_monatsauswertung_abdeckung_n92.py` — eine Summe darf 0 bleiben, eine
  Differenz nicht.
- `backend/tests/test_n121_monate_ohne_db_spur.py` — was aus Tageswerten stammt, sagt es.
- Im Frontend `TagWerteTabelle.test.tsx` und `JahrVerlaufChart.test.tsx` — unterdrückte Werte
  tragen „—" und der Tooltip nennt den Grund. **Seit 29.08. zusätzlich die Subtrahenden**
  (N-95): `erfassteSenken` trennt „Gerät gibt es nicht" von „diese Stunde fehlt", indem es
  den **Tag** fragt statt den Einzelwert — dieselbe Träger-Idee wie `TagesBilanz.*_erfasst`.
  Die additive Schwester „Verfügbare Energie" wird **beschriftet** statt unterdrückt (N-94).
