# Konzept — Monats-Fakten: die fehlende Aufbereitungs-Schicht

> **Status: UMGESETZT (2026-07-31).** Alle sechs Bau-Schritte sind gebaut; der
> Bauplan unten ist Historie, nicht Arbeitsvorrat. Das Dokument bleibt
> versioniert, weil **ADR-002/P10 darauf verweist** — es ist die Begründung
> hinter der Regel, nicht ihr Ersatz.
>
> **Wo der laufende Stand steht — dieses Dokument wird nicht mehr fortgeschrieben:**
>
> | Was | Dauerhafte Heimat |
> | --- | --- |
> | Die Regel selbst + „gesichert durch" je Schritt | [`docs/ADR-002-WURZELMUSTER.md`](ADR-002-WURZELMUSTER.md), Zeile **P10** |
> | Migrationsstand + die drei Wächter-Kategorien mit ihren Zahlen | [`docs/ARCHITEKTUR.md`](ARCHITEKTUR.md) §7 |
> | Der Kontrakt für Aufrufer (`lade_monats_fakten`, Feldgruppen, Fallen) | Modul- und Dataclass-Docstrings in `eedc/backend/services/monats_fakten.py` |
> | Die gezählte Restschuld | `P10_NOCH_NICHT_MIGRIERT` im Wächter selbst (**2** nach C1b), mit Obergrenze im Test |
> | Nebenfunde N-2 … N-17 (Abarbeitung nach S6) | `~/.claude/plans/uebergabe-monats-fakten.md` |
>
> **Eine der umgehängten Sichten gibt es nicht mehr:** `cockpit/social.py` (S3,
> geteilter Monatstext) ist am 2026-07-31 **zurückgebaut** worden — die
> Oberfläche dazu war beim IA-V4-Flip entfallen, der Endpoint lief ohne
> Konsumenten (Nebenfunde-Runde, Paket B). Die Bau-Tabellen unten bleiben als
> Historie unverändert; wer `social.py` sucht, findet es nur noch dort.
>
> **Was nach S6 offen bleibt** — beides bewusst *nicht* in diesem Dokument
> geparkt, sondern an den genannten Stellen benannt und gezählt:
>
> 1. **Die Nebenfunde-Runde** (12 offene Einträge im Register) — erst
>    analysieren, was sich durch die Migration erledigt hat, dann abarbeiten.
> 2. **`MonatsFakt.je_investition`** — der Ausbau, der `P10_PER_INVESTITION`
>    (11 Funktionen) leert. Entscheid **N-2**: vertagt, nicht verworfen.
> 3. **F-6** (Tages-CO₂ auf dem Eigenverbrauch) — Nicht-Ziel dieser Schicht
>    (§4), ein eigener Einzelfix im Tages-Pfad.
>
> ---
>
> **Status bis dahin: ABGENOMMEN (Gernot, 2026-07-31).** Bau beginnt mit S1.
> Auslöser: Drift-Inventur 2026-07-31 (`~/.claude/plans/inventur-drift-oberflaeche.md`),
> sechs bestätigte Befunde, alle aus derselben Ursache.
>
> **Abnahme-Entscheidungen** (lösen §11 ab):
> 1. **Reichweite: alle sechs Schritte** — auch S4 (Cockpit/HA-Export, heute
>    korrekt) wird nachgezogen. Begründung der Vollständigkeit: eine Sicht, die
>    weiter selbst faltet, ist die nächste Drift-Quelle, auch wenn sie heute
>    stimmt.
> 2. **Community (S6) wird mitgezogen** — inklusive Datenmodell-Abgleich mit
>    `eedc-community`. Beide Repos synchron oder gar nicht.
> 3. **Release-Schnitt: alles zusammen** — die derzeit unveröffentlichten
>    Commits (P8, P9, USt, historische Tarife) warten auf den Abschluss dieses
>    Strangs. *Konsequenz, bewusst getragen:* diese Korrekturen erreichen HA-
>    Nutzer erst danach. Meldet ein Tester zwischenzeitlich genau einen dieser
>    Fehler, ist ein Zwischen-Release jederzeit möglich — das entscheidet der
>    Maintainer dann, nicht dieses Konzept.

## 1. Ausgangslage — was die Inventur gemessen hat

Der Berechnungs-Layer (ADR-001, `core/berechnungen/`) ist **fehlerfrei**. Die
Inventur über 23 Sichten × 18 kanonische Größen fand keinen einzigen Rechenfehler.
Sie fand sechsmal dieselbe Struktur: **jede Sicht faltet die Rohdaten selbst zu
Monatswerten**, und dabei fällt jedes Mal etwas anderes weg.

Der härteste Beleg, gemessen an einer Anlage, die nur das Anlagen-Aggregat pflegt
(PV-Modul ohne eigene IMD-Zeile — der Normalfall bei manueller Pflege und bei
Importen mit einem Gesamt-PV-Sensor):

| Sicht | PV | Netto-Ertrag |
| --- | --- | --- |
| Cockpit · HA-Export | 1.000 kWh | 212,00 € |
| Aussichten · Jahresbericht-PDF | 0 kWh | **32,00 €** |

85 % Abweichung, weil zwei Sichten `lade_pv_je_monat` nutzen und fünf roh
`verbrauch_daten["pv_erzeugung_kwh"]` summieren. Analog fehlen anderswo V2H, der
Erzeuger hinter dem Zähler, der Monatstarif oder der Dienstwagen-Filter.

**Warum kein Test das fängt:** Symmetrie-Tests decken nur die Achsen ab, die ihre
Fixture variiert. Die Vier-Wege-Fixture seedet immer Pro-Modul-IMD.

## 2. Der Präzedenzfall — das hier ist keine Erfindung

`services/pv_monatswerte.py` **ist bereits diese Schicht, für genau eine Größe.**
Sein Docstring beschreibt exakt dasselbe Problem („die Eingabe musste bisher jede
Read-Site selbst zusammensuchen … zwei davon sind an der Formel vorbeigelaufen")
und dieselbe Lösung. Seit es ihn gibt, ist in der PV-Auflösung **keine neue Drift**
entstanden — die verbleibenden Befunde sind genau die Sichten, die ihn *nicht*
benutzen.

Dieses Konzept verallgemeinert diese Bauform von einer Größe auf die Monatszeile.
Dieselbe Schichtung, dieselbe Rückgabeform, dieselbe Wächter-Idee.

## 3. Kontrakt

```
lade_monats_fakten(db, anlage_id, *, von=None, bis=None) -> list[MonatsFakt]
```

**Ein `MonatsFakt` ist die vollständige, kanonisch aufgelöste Wahrheit über einen
Monat einer Anlage.** Wer ihn hat, braucht keine ORM-Zeile mehr anzufassen und
trifft keine Auflösungsentscheidung mehr selbst.

Er wird **einmal je Anfrage** gebaut (ein Query-Satz, danach reine Faltung) und von
allen aggregierenden Sichten geteilt.

### Feldgruppen

| Gruppe | Inhalt | kanonische Quelle |
| --- | --- | --- |
| `zaehler` | einspeisung, netzbezug | `Monatsdaten` |
| `erzeugung` | pv_module (P7-aufgelöst) · bkw · sonstige_erzeuger · **erzeugung_hinter_zaehler** | `lade_pv_je_monat` · `imd_typ_beitrag` · `erzeugung_hinter_zaehler_kwh` |
| `bkw` | rest_eigenverbrauch (P9) | `bkw_finanz_beitrag` |
| `speicher` | ladung · entladung · netzladung · ladepreis | `imd_typ_beitrag` |
| `emob` | pool (ladung/pv/netz/extern) · km · v2h — **ohne Dienstwagen** | `get_emob_heimladung_canonical` · `ist_dienstlich` |
| `wp` | strom · wärme · heizung · warmwasser · split | `imd_typ_beitrag` |
| `sonstiges` | verbrauch · netto_euro | `berechne_sonstige_netto` + Basis-Positionen |
| `tarif` | netzbezug_preis (flex-aufgelöst) · einspeisevergütung · grundpreis · wp-/wallbox-Spezialtarif | `lade_tarife_fuer_anlage(target_date=)` (P8) |
| `eeg` | neg_preis_kwh (§51) | `get_neg_preis_einspeisung_monat` |
| `kennzahlen` | eigenverbrauch · direktverbrauch · gesamtverbrauch · autarkie · quoten | `berechne_verbrauchs_kennzahlen` |
| `meta` | aktive Investitionen · Vollständigkeit der PV-Auflösung (N42) · Quelle | — |

**Alle Zeitfilter (aktiv · Anschaffung · Stilllegung) und der Dienstwagen-Filter
werden genau hier angewandt, einmal.**

### Schichtung (ADR-001)

- **Formeln bleiben, wo sie sind** — `core/berechnungen/` wird nicht angefasst.
  Die Schicht *ruft* sie, sie kopiert nichts.
- **DB-I/O in `services/`** — wie `pv_monatswerte.py` und `finanz_zeilen.py`.
- `baue_finanz_zeile` wird **Konsument**: `FinanzZeileEingabe` entsteht aus einem
  `MonatsFakt` statt aus 12 site-eigenen Dicts.

## 4. Nicht-Ziele (bewusst außerhalb)

- **Tages- und Stundenebene.** Der Tag hat eine eigene, korrekte Quelle
  (`bilanz_aus_stundenrows` über Snapshots). Befund **F-6** (Tages-CO₂ auf der
  Erzeugung statt auf dem Eigenverbrauch) bleibt deshalb ein Einzelfix und wird
  von dieser Schicht **nicht** miterledigt.
- **Live** und **Prognose** — andere Quellen, andere Zeitachse.
- **Schreibpfade** (Monatsabschluss, Import, Connector) — die Schicht ist reines Lesen.

## 5. Migration — additiv, Sicht für Sicht

Kein Big Bang. Jeder Schritt ist für sich lauffähig und abbrechbar:

| # | Schritt | Fixture-Achse, die den Schritt beweist |
| --- | --- | --- |
| 1 | Schicht bauen, keine Sicht umgehängt | Einheitstests der Auflösung je Gruppe |
| 2 | **Aussichten** + **Jahresbericht-PDF** + **Investitions-ROI** umhängen | Anlage **ohne** Pro-Modul-IMD (F-5) |
| 3 | **Cockpit/CO₂** + **Cockpit/Social** umhängen | Anlage mit **V2H** *und* Erzeuger hinter dem Zähler (F-1) |
| 4 | **Cockpit/Übersicht** + **HA-Export** nachziehen (heute korrekt, aber eigene Faltung) | bestehende Vier-Wege-Symmetrie muss unverändert grün bleiben |
| 5 | **Komponenten-Dashboards** umhängen | Dienstwagen-Anlage (F-7) · BKW ohne gemessenen EV (F-4) |
| 6 | **Community-Payload** — nur mit Datenmodell-Abgleich `eedc-community` | Anlage ohne Pro-Modul-IMD |

Nach jedem Schritt: volle Gates, und die Vier-Wege-Symmetrie um die jeweilige
Achse erweitert — **sonst wiederholt sich genau die Blindstelle**, die diese
Befunde erst möglich gemacht hat.

## 6. Wächter

Bauform wie ADR-002/P9, aber auf der Eingabe-Ebene statt feldweise:

- **AST, baumweit:** außerhalb von `services/monats_fakten.py` (und der benannten
  Schreibpfade) darf keine Produktivdatei mehr `InvestitionMonatsdaten` selbst
  laden und zu `(jahr, monat)` falten. Baseline wird mit klassifizierten Ausnahmen
  bei 0 gesetzt — die Ausnahmen sind die Schreib-/Import-/Checker-Pfade.
- Der bestehende `test_finanz_monatszeile_nur_im_builder` bleibt und bekommt einen
  Nachbarn: `FinanzZeileEingabe` nur noch aus einem `MonatsFakt`.

Als neue **ADR-002/P10** eintragen, mit „gesichert durch"-Spalte.

> **Gebaut mit S5 (2026-07-31) — zwei Abweichungen vom Entwurf oben, beide
> gemessen begründet und von Gernot entschieden:**
>
> 1. **Funktions-granular statt modul-granular.** Eine Ausnahme auf Dateiebene
>    hätte `dashboards.py`, `ha_export.py` und `aussichten.py` komplett
>    freigestellt — also genau die Dateien, die der Auftrag ohnehin anfasst.
>    Der Schlüssel ist `modul.py::funktion`; eine **neue** Funktion in einer
>    ausgenommenen Datei ist ein Treffer.
> 2. **Drei Ausnahme-Kategorien statt einer.** „Baseline 0 mit nur Schreib-,
>    Import- und Checker-Ausnahmen" war **nicht erreichbar** — gemessen falteten
>    beim Scharfstellen noch sechs Lese-Sichten selbst, davon drei
>    (`monatsdaten.py`, `aktueller_monat.py`, `cockpit/komponenten.py`), die in
>    §5 nie vorkamen — zwei davon sind mit **C1a** und **C1b** (2026-08-03)
>    umgehängt, offen ist nur noch `aktueller_monat.py`. Sie in eine
>    Sammel-Ausnahme zu schieben hätte den Wächter
>    zu dem Aufräum-Paket gemacht, das ADR-002 §„noch nicht gewächtert" ablehnt.
>    Stattdessen: `P10_SCHREIBEN_IMPORT_CHECKER` (dauerhaft legitim) ·
>    `P10_PER_INVESTITION` (Aggregat je Gerät — die Schicht hat dafür keine
>    Sicht, Register N-2) · `P10_NOCH_NICHT_MIGRIERT` (**anlagenweite Faltung,
>    also die Klasse, gegen die P10 gebaut ist**) — letztere mit einer
>    **Obergrenze im Test**, damit die Restschuld eine Zahl ist und nur fallen
>    kann.
>
> Der **Tages-Pfad** (`energie_profil/views.py`, `energie_profil/tage_werte.py`)
> baut eine `FinanzZeileEingabe` und ist trotzdem klassifizierte Ausnahme: seine
> Mengen kommen aus `bilanz_aus_stundenrows`, `jahr`/`monat` trägt er nur für den
> Tarif-Stichtag (P8) und §51. Ihn auf die Schicht zu ziehen wäre kein Fix,
> sondern eine andere Zahl (§4).

## 7. Risiken, benannt

1. **Zahlen bewegen sich.** Das ist der Zweck (fünf Sichten rechnen heute falsch),
   aber es trifft Anwender sichtbar — insbesondere ROI, Amortisation und den
   Jahresbericht. Braucht eine eigene WAS-IST-NEU-Passage.
2. **Ladezeit.** Heute lädt jede Sicht gezielt; die Schicht lädt den ganzen Monat.
   Gegenmaßnahme: ein Query-Satz je Anfrage + Request-Cache, und die
   Ladezeit-Messung aus `KONZEPT-LADEZEIT-CACHE-SWR.md` vor/nach vergleichen.
   **Abbruchkriterium:** wird Cockpit/Übersicht messbar langsamer, wird Schritt 4
   zurückgestellt.
3. **Cross-Repo.** Schritt 6 berührt das Community-Datenmodell — beide Repos
   synchron oder gar nicht.
4. **Umfang.** Sechs Schritte, jeder mit Gates. Das ist keine Runde, das sind
   mehrere — das Release der 10 fertigen Commits verschiebt sich entsprechend,
   falls es daran hängt.

## 8. Abnahmekriterien

- Die Vier-Wege-Symmetrie ist um **drei** Achsen erweitert (kein Pro-Modul-IMD ·
  V2H · Erzeuger hinter dem Zähler) und grün.
- Die fünf F-5-Sichten nennen für die Aggregat-Anlage 212,00 € statt 32,00 €.
- Der P10-Wächter steht auf Baseline 0 und ist ohne den Umbau als rot verifiziert.
- Keine Sicht lädt `InvestitionMonatsdaten` mehr selbst, außer den benannten
  Ausnahmen.
- Ladezeit Cockpit/Übersicht nicht schlechter als vorher (gemessen, nicht geschätzt).

## 9. Dokumentations-Pflichten (Teil des Bauauftrags, nicht Nacharbeit)

Ein Fundament-Paket, das die Doku nicht mitzieht, hinterlässt eine SoT-Lüge. Wer
welchen Schritt baut, zieht **im selben Paket** nach:

| Dokument | Was hinein muss | Bei welchem Schritt |
| --- | --- | --- |
| `docs/ADR-002-WURZELMUSTER.md` | **P10** als Regel + „gesichert durch"-Spalte (Wächter/Regression getrennt); Titel/Zählung von „Neun" auf „Zehn" | Schritt 1 |
| `docs/ADR-001-BERECHNUNGS-LAYER.md` | Die Schicht ist **Eingabe-Aufbereitung, nicht Formel** — Abgrenzung zu `core/berechnungen/` explizit; die Drei-Punkte-Pflicht (Builder + Wächter + Symmetrie-Test) um „Fakten-Quelle" erweitern | Schritt 1 |
| `docs/ARCHITEKTUR.md` | `services/monats_fakten.py` in der Schichtenübersicht; die Aussage „jede Read-Site aggregiert selbst" ist danach falsch | Schritt 1 |
| `docs/BERECHNUNGEN.md` | §1 nennt heute nur `lade_pv_je_monat` als Lesequelle (P7). Ergänzen: die Monats-Fakten sind ab jetzt **die** Lesequelle, PV darin ein Feld | Schritt 2 |
| `CLAUDE.md` | SoT-Regime-Tabelle (P1–P10) · „Kritische Code-Patterns" um den Fakten-Zugriff ergänzen · Digest-Eintrag beim Release | Schritt 1 + Release |
| `CHANGELOG.md` / WAS-IST-NEU | Anwender-Sicht: **welche Zahlen sich bewegen und warum** (ROI, Amortisation, Jahresbericht, CO₂) | beim Release |
| `docs/KONZEPT-MONATS-FAKTEN.md` (dieses) | ✅ mit der Abnahme aus `drafts/` nach `docs/` gewandert — **weil ADR-002/P10 darauf verweisen wird und ein versionierter Verweis nicht ins Gitignore zeigen darf**. Nicht auf der Website: `website/scripts/sync-docs.sh` arbeitet mit einer Allowlist, in der Konzepte und ADRs bewusst fehlen. Nach S6: Stand fortschreiben, Restposten an eine dauerhafte Heimat | ✅ **erledigt mit S6** — der Kopf trägt die Wanderungskarte (wo der laufende Stand jetzt steht) und die drei offenen Punkte; ab hier ist das Dokument Historie und wird nicht mehr fortgeschrieben |
| GitHub **#110** | Sammelzeile „Monats-Fakten-Schicht" mit Schritt-Stand | nach Abnahme |

Die Website zieht `docs/` automatisch (`scripts/sync-docs.sh`) — kein separater Schritt.

## 10. Session-Plan

Sechs Bau-Schritte, geschnitten nach dem, was in **eine** Session passt (jeweils
volle Gates + Rot-Verifikation am Ende). Reihenfolge ist bindend: Schritt 1 trägt
alle anderen.

| Session | Inhalt | Größe | Abschluss |
| --- | --- | --- | --- |
| **S1** | Schicht + Kontrakt + Einheitstests je Feldgruppe. **Keine** Sicht umgehängt. P10-Wächter noch nicht scharf (er würde alle Sichten melden). ADR-001/ADR-002/ARCHITEKTUR nachziehen. | groß | Schicht steht, Baum unverändert grün |
| **S2** | **F-5**: Aussichten · Jahresbericht-PDF · Investitions-ROI umhängen. Vier-Wege-Symmetrie um die Achse „ohne Pro-Modul-IMD" erweitern. BERECHNUNGEN §1 nachziehen. | groß | 212,00 € statt 32,00 € in allen fünf Sichten |
| **S3** | **F-1**: Cockpit/CO₂ + Cockpit/Social umhängen. Achse „V2H + Erzeuger hinter dem Zähler". Hartkodierte 7 l/100 km auf `vergleich_l_100km`. | mittel | CO₂/Autarkie deckungsgleich mit dem Cockpit |
| **S4** | Cockpit/Übersicht + HA-Export nachziehen (heute korrekt → reiner Strukturschritt). **Ladezeit vorher/nachher messen.** | mittel | Vier-Wege-Symmetrie unverändert grün, Ladezeit nicht schlechter |
| **S5** ✅ | **F-4 + F-7**: Komponenten-Dashboards umhängen (BKW-Tarif, Dienstwagen-Filter). P10-Wächter **scharf stellen**, Baseline 0 mit klassifizierten Ausnahmen. | mittel | Wächter grün, ohne Umbau rot verifiziert |
| **S6** ✅ | Community-Payload — **nur** mit Datenmodell-Abgleich `eedc-community`. Optional, eigener Entscheid. | klein | beide Repos synchron |

> **Gebaut mit S6 (2026-07-31) — was der Schritt gegenüber dem Entwurf gelernt hat:**
>
> 1. **Der Payload verlor drei Achsen, nicht eine.** Die Inventur hatte diese
>    Sicht nur auf **F-5** abgeklopft (§1). Gemessen fehlten außerdem **F-1**
>    (V2H + Erzeuger hinter dem Zähler in der Autarkie: 85,7 % statt 90,9 %)
>    und der **Dienstwagen-Filter** — km, Ladung und V2H eines dienstlichen
>    Fahrzeugs gingen in den öffentlichen Benchmark ein. Dazu die #262-Klasse:
>    der Netz-Anteil wurde roh gelesen statt abgeleitet (150 statt 200 kWh bei
>    evcc-Import).
> 2. **F-5 wiegt hier schwerer als in den Finanz-Sichten.** Dort waren es 32 €
>    statt 212 €. Hier blieb `monatswerte` **leer**, und `/community/share`
>    antwortet darauf mit HTTP 400: die betroffenen Anlagen konnten am
>    Benchmark gar nicht teilnehmen.
> 3. **§11 hieß nicht automatisch „Schema ändern".** `eedc-community/backend/
>    schemas.py` blieb strukturell unverändert — der Payload validiert
>    unverändert (end-to-end geprüft, nicht behauptet). Geändert hat sich die
>    **Bedeutung** dreier Feldgruppen, und weil der Server nichts nachrechnet,
>    ist genau diese Semantik im selben Paket als Vertrag in den Docstring von
>    `MonatswertInput` gewandert. „Beide Repos oder gar nicht" ist damit erfüllt,
>    ohne eine Migration zu erfinden, die niemand braucht.
> 4. **Zwei Gernot-Entscheide (31.07.), beide mit Messung vorgelegt:**
>    Dienstwagen **raus** aus den E-Mob-Mengen (die stehende Regel gilt auch für
>    den Benchmark, Preis: die öffentliche Summe „X km elektrisch gefahren"
>    sinkt) · Altbestand auf dem Server **stehen lassen** — der Submit ist ein
>    Voll-Submit, jede Anlage heilt beim nächsten Teilen. Keine Start-Migration,
>    kein erzwungener Re-Share, keine Markierung.
> 5. **Die Schicht musste dafür eine Quellen-Trennung bekommen.** Der Server
>    führt `eauto_*` und `wallbox_*` als getrennte Felder; der Heimladungs-Pool
>    wählt aber genau EINE Quelle. Neu: `EmobFakten.eauto_summe` /
>    `wallbox_summe` über denselben SoT-Leser (`summiere_emob_quelle`, dafür
>    öffentlich gemacht) — getrennt, aber nicht roh gelesen.

**Daneben, unabhängig und jederzeit einschiebbar:** **F-6** (Tages-CO₂ auf dem
Eigenverbrauch statt auf der Erzeugung) — ein Einzelfix im Tages-Pfad, den diese
Schicht bewusst nicht abdeckt (§4).

## 11. Entschieden (2026-07-31)

Die drei offenen Punkte sind abgenommen — Wortlaut im Kopf dieses Dokuments.
Alle sechs Schritte, Community mitgezogen, ein gemeinsames Release am Ende.

**Was daraus folgt und beim Bau gilt:**

- **S4 ist kein optionaler Schönheitsschritt.** Cockpit und HA-Export rechnen
  heute richtig; sie werden trotzdem umgehängt, weil eine selbst faltende Sicht
  die nächste Drift-Quelle ist. Der Beweis für S4 ist deshalb nicht eine neue
  Zahl, sondern: **die bestehende Vier-Wege-Symmetrie bleibt unverändert grün**
  — plus die Ladezeit-Messung aus §7.
- **S6 koppelt zwei Repos.** `eedc-community/backend/schemas.py` und
  `eedc/backend/services/community_service.py` werden im selben Paket angefasst
  oder gar nicht. Ein halb migrierter Payload ist schlimmer als der heutige.
  > **Ausgang (2026-07-31):** beide Repos im selben Paket angefasst — die
  > Struktur blieb, die **Semantik** ist gewandert. Kein Feld kam hinzu, keines
  > fiel weg, keine Grenze verschob sich; geprüft wurde end-to-end, indem der
  > erzeugte Payload gegen das Schema des anderen Repos instanziiert wurde.
  > `MonatswertInput` trägt seither die Bedeutung der drei geänderten
  > Feldgruppen im Docstring — der Server rechnet nichts nach, also muss sie
  > dort stehen, wo sie gelesen wird. Ein „halb migrierter Payload" ist damit
  > ausgeschlossen, ohne eine Schema-Migration zu erfinden.
- **Kein Zwischen-Release.** Der Strang läuft bis S6 durch. Wer unterwegs eine
  Zahl bewegt, schreibt die Anwender-Sicht **sofort** in den
  WAS-IST-NEU-Entwurf — am Ende sind es sechs Sessions Abstand zur Erinnerung.
