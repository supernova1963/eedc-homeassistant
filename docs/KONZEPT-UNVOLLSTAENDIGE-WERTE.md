# Regel — was eedc sagt, wenn ein Messwert fehlt

> ## **Status (gemessen 2026-08-28): die Regel gilt und ist gewächtert**
>
> **Was hier steht:** wie eedc mit einem fehlenden Messwert umgeht — und warum es ihn **nicht**
> durch 0 ersetzt. §3 ist die tragende Regel; **23 Stellen im Code zitieren sie**, dazu
> [BERECHNUNGEN.md](BERECHNUNGEN.md). §6 nennt die Regressionen, die sie halten.
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
| `services/monats_fakten.py:654-655` | `einspeisung_kwh=(monatsdaten.einspeisung_kwh or 0.0) if monatsdaten else 0.0` — Ziel ist `ZaehlerFakten.einspeisung_kwh: float = 0.0` (`:108-112`). Die NULL-Spalte in `Monatsdaten` **weiß** es; die Schicht wirft es hier weg |
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
| `api/routes/prognosen.py:763` | `ist_heute_kwh=round(…) if ist_heute_kwh > 0 else None` — exakt 0 wird `null`, und `fmtZahl(null)` zeigt „—". Die Ironie: **`ist_unvollstaendig` steht als eigenes Flag im selben Response** (`:766`), wird hier aber nicht benutzt (**N-52**) |
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

**Kein einziger Konsument liest es** — keine Route, kein Schema, keine Zeile im
Frontend. Das Flag ist vollständig implementiert, getestet und **erreicht die
Antwort nie**. Wer die PV-Achse liest (`pv_kwh` — spezifischer Ertrag,
Performance Ratio, SOLL/IST, Finanz-Zeile), bekommt bei fehlendem Modulwert eine
Teilsumme ohne jeden Hinweis, obwohl die Schicht zwei Zeilen darüber genau weiß,
dass sie unvollständig ist.

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

Geprüft wird deshalb am Ergebnis, und dafür stehen fünf Regressionen (gemessen 2026-08-28):

- `backend/tests/test_tagesbilanz_pv_nicht_erfasst.py` — eine additive Größe ohne Messung wird
  unterdrückt statt als 0 geführt.
- `backend/tests/test_live_tageswerte_luecken.py` — der Auslöserfall (Rainer): fällt ein Summand
  aus, verschwindet die Differenz, statt zu hoch zu stehen.
- `backend/tests/test_monatsauswertung_abdeckung_n92.py` — eine Summe darf 0 bleiben, eine
  Differenz nicht.
- `backend/tests/test_n121_monate_ohne_db_spur.py` — was aus Tageswerten stammt, sagt es.
- Im Frontend `TagWerteTabelle.test.tsx` und `JahrVerlaufChart.test.tsx` — unterdrückte Werte
  tragen „—" und der Tooltip nennt den Grund.
