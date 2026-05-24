# Übergabe: LTS-Aggregator-Drift in `komponenten_kwh` — vollständige Bereinigung

> **Stand:** 2026-05-24 nach Diagnose-Session mit Gernot. Diese Datei ist self-contained — die nächste Session braucht keinen Conversation-Kontext, nur dieses Dokument + den Code-Stand.
>
> **Empfohlener Release:** v3.33.0 (zu groß für ein Patch-Release, eigene semantische Korrektur historischer Werte).

---

## TL;DR

Seit **v3.31.0 (2026-05-16, Commit `e493fc8d`)** schreibt `aggregate_day` für HA-Add-on-User die `TagesZusammenfassung.komponenten_kwh` über einen LTS-Aggregator-Pfad ([`backend/services/snapshot/lts_aggregator.py::get_komponenten_tageskwh_lts`](../../eedc/backend/services/snapshot/lts_aggregator.py)), der **alle gemappten Sensoren einer Investition unter demselben Komponenten-Key aufaddiert** — ohne die typ-spezifischen Filter, die der Snapshot-Pfad ([`backend/services/snapshot/aggregator.py::get_komponenten_tageskwh`](../../eedc/backend/services/snapshot/aggregator.py)) konsequent anwendet.

Folgen pro Komponententyp siehe Abschnitt „Drift-Matrix" unten. Sichtbar gemeldet wurde es bei detLAN ([#290](https://github.com/supernova1963/eedc-homeassistant/issues/290)) für die Wärmepumpe (Faktor ~8,5×). Verifiziert wurde es zusätzlich an Gernots eigener Anlage (Anlage „Winterborn"): Wallbox-Tagessumme zeigte 23,24 kWh statt korrekt 14 kWh (+66 % Übertreibung) am 22.5.2026.

Schreibpfade waren **autonom aktiv** (Scheduler alle 15 Min, Monatsabschluss, Werkbank-Reaggregate, Vollbackfill) — der gesamte Anwenderkreis HA-Add-on mit Multi-Sensor-Mappings hat seit dem 16.5. korrupte Werte in der DB.

---

## Ziel dieser Übergabe

1. **Strukturellen Root-Cause-Fix** in der LTS-Variante, geometrisch garantiert symmetrisch zur Snapshot-Variante (geteilter Helper).
2. **Parametrisierter Symmetrie-Test** der für jeden Typ + Mapping-Permutation beide Aggregator-Varianten gegeneinander prüft. Wäre der eine Test gewesen, der den Bug am 16.5. abgefangen hätte.
3. **Erweiterte Invariante** `pruefe_tep_tz_konsistenz` von PV+BKW auf alle Komponenten — zukünftige Drifts loggen sich selbst.
4. **Historische Bereinigung** aller TZ-Rows zwischen 2026-05-16 und Update-Datum. Ohne diese bleiben die alten falschen `komponenten_kwh`-Werte stehen — der Scheduler überschreibt nur heute + gestern.
5. **Daten-Checker-Erweiterung** (optional, defense-in-depth): drift-Diagnose-Kategorie sichtbar machen.

---

## Bisheriger Stand (uncommitted lokal)

In dieser Session wurden **Symptom-Patches** im Zuge der Diagnose von #290 / #291 eingebaut. Sie sind **noch nicht commited**, aber stabil und 479/479 Tests grün. Vor dem Root-Cause-Fix entscheiden, welche bleiben.

**Datei-Modifikationen:**

| Datei | Was | Bewertung |
|---|---|---|
| `eedc/backend/services/energie_profil/backfill.py` | Per-Tag-Commit in `backfill_range` und `backfill_from_statistics` (#291 Database-Lock) | **Behalten.** Unabhängig vom LTS-Bug, eigene Wurzel. |
| `eedc/backend/services/energie_profil/scheduler_jobs.py` | Per-Anlage-Commit in `aggregate_today_all` / `aggregate_yesterday_all` (#291) | **Behalten.** Wie oben. |
| `eedc/backend/core/database.py` | `busy_timeout` 10s → 30s (#291) | **Behalten.** |
| `eedc/backend/api/routes/monatsabschluss/wizard.py` | `_ist_lock_fehler` + `_wizard_save_fehler` (#291 freundliche 503 statt SQL-Dump) | **Behalten.** |
| `eedc/backend/api/routes/energie_profil/repair.py` | `_stunden_mit_messdaten` Field-Restore (#290 Bug D — beim Orchestrator-Refactor in Commit `17db2350` verloren gegangen) | **Behalten.** Eigenständiger Refactor-Regress. |
| `eedc/backend/services/snapshot/aggregator.py` | Docstring-Fix (#290 Bug C — Docstring sagte „Σ stromverbrauch+heizenergie+warmwasser", Code rechnete nur stromverbrauch) | **Behalten.** Cosmetic + Maintainer-Klarheit. |
| `eedc/backend/services/energie_profil/aggregator.py` | (a) preserve `komponenten_kwh` bei `datenquelle=="manuell"` + leerem Σ-Hourly. (b) Skip `boundary_kwh` für `datum >= today` und für `datenquelle=="manuell"`. (#290 Bug A + B) | **Defense-in-depth, behalten** — auch nach Root-Cause-Fix sinnvoll, weil beide Pfade dann zwar konsistent sind, aber bei `today` ist `snap[Folgetag 00:00]` weiterhin futurum und Self-Heal-Risiko bleibt. Schutz kostet nichts. |
| `eedc/frontend/src/components/energieprofil/EnergieprofilTageTabelle.tsx` | Einheits-Suffix im Spaltenheader (#290 Punkt 5) | **Behalten.** |
| `eedc/frontend/src/pages/WaermepumpeDashboard.tsx` | „(Lebensdauer)"-Suffix am KPI-Titel (#290 Punkt 1) | **Behalten.** |

**Neue Test-Dateien:**
- `eedc/backend/tests/test_aggregator_290_preserve.py` — 3 Tests für preserve-Logik + today-skip
- `eedc/backend/tests/test_backfill_per_tag_commit.py` — 2 Tests für #291 per-day-commit
- `eedc/backend/tests/test_monatsabschluss_lock_handling.py` — 5 Tests für #291 Lock-Erkennung

**Suite:** 479 grün. **TypeScript:** clean.

---

## Root Cause: vollständige Drift-Matrix Snapshot vs LTS

Beide Funktionen produzieren `{komponenten_key: tages_kwh}` mit identischer Key-Konvention. Hier was sie pro `inv.typ` aus dem Sensor-Mapping holen:

| Typ | Snapshot-Variante (korrekt, [aggregator.py:444-516](../../eedc/backend/services/snapshot/aggregator.py#L444-L516)) | LTS-Variante (Bug, [lts_aggregator.py:245-279](../../eedc/backend/services/snapshot/lts_aggregator.py#L245-L279)) | Drift |
|---|---|---|---|
| **pv-module** | `pv_erzeugung_kwh` only → `pv_<id>` | **Alle gemappten Felder** → `pv_<id>` mit `+1` | Latent. `KUMULATIVE_ZAEHLER_FELDER["pv-module"]` hat nur `pv_erzeugung_kwh`, realistisch kein Drift. |
| **balkonkraftwerk** | dito → `bkw_<id>` | Alle → `bkw_<id>` mit `+1` | Latent (wie pv-module). |
| **speicher** | `ladung_kwh` (+) und `entladung_kwh` (−) → `batterie_<id>` (signed). **`ladung_netz_kwh` ignoriert.** | Alle mit `+1`, nur `entladung_kwh` mit `−1`. **`ladung_netz_kwh` wird `+1` addiert.** | **AKUT** für Arbitrage-Anwender. `ladung_netz_kwh` ist semantisch Teilmenge von `ladung_kwh` → Doppelzählung. |
| **waermepumpe** | `stromverbrauch_kwh` ODER (bei `getrennte_strommessung`) `strom_heizen + strom_warmwasser` → `waermepumpe_<id>`. **Nur Strom.** | Alle: `stromverbrauch + heizenergie + warmwasser + strom_heizen + strom_warmwasser + wp_starts_anzahl + wp_betriebsstunden` | **AKUT detLAN**: Faktor 5–10× bei vollem Mapping (Strom + Thermisch × COP). Plus `KUMULATIVE_COUNTER_FELDER` (Starts-Anzahl, h) werden als kWh interpretiert. |
| **wallbox** | `ladung_kwh` only → `wallbox_<id>` | Alle: `ladung + ladung_pv + ladung_netz` mit `+1` | **AKUT Gernot**: `ladung_pv_kwh` und `ladung_netz_kwh` sind Teilmengen von `ladung_kwh`. Verifiziert am 22.5.2026: korrekt 14 kWh, falsch 23.24 kWh. |
| **e-auto** | `ladung_kwh` ODER Fallback `verbrauch_kwh` → `eauto_<id>`. **Skip wenn `parent_investition_id` (Wallbox misst).** | Alle: `ladung + verbrauch + ladung_pv + ladung_netz`. **Kein parent-Filter, kein Either-Or.** | **AKUT**: Wallbox-misst-EA-Konstellation → Doppelzählung Haushaltsverbrauch. Plus Split-Sensor-Doppelzählung. |
| **sonstiges** | Primary (`erzeugung_kwh` für Erzeuger, `verbrauch_kwh` für Verbraucher) ODER Fallback secondary → `sonstige_<id>`. **Genau eines, immer ≥0.** | `verbrauch_kwh` mit `−1` bei Verbraucher (+1 bei Erzeuger), `erzeugung_kwh` immer `+1`. **Beide gemappt → `erzeugung − verbrauch`.** | **AKUT** bei bidirektional gemappten Sensoren (Hybridgerät). |
| **basis: einspeisung / netzbezug** | jeweils einzeln, ≥0 Schwelle | jeweils einzeln, `+1` | Konsistent. |

**Plus latent:** `KUMULATIVE_COUNTER_FELDER` für WP (`wp_starts_anzahl`, `wp_betriebsstunden`) sind Zähler, kein kWh. Werden vom LTS-Aggregator über die generische Schleife in `waermepumpe_<id>` einsummiert als wären's kWh.

---

## Fix-Architektur

### Phase 1: Geteilter Helper

**Datei (neu):** `eedc/backend/services/snapshot/komponenten_beitraege.py`

Eine Funktion, die für eine Investition (oder Basis-Mapping) eindeutig die Liste `(feld, target_key, vorzeichen)` liefert, die in `komponenten_kwh.<target_key>` einfließen soll:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class KomponentenBeitrag:
    feld: str          # z.B. "ladung_kwh", "stromverbrauch_kwh"
    target_key: str    # z.B. "wallbox_2", "waermepumpe_5"
    vorzeichen: int    # +1 oder -1

def basis_beitraege(sensor_mapping: dict) -> list[KomponentenBeitrag]:
    """einspeisung + netzbezug aus basis-Mapping. Liefert nur Felder mit
    Strategie 'sensor' und gesetzter sensor_id."""

def investition_beitraege(
    inv,  # backend.models.investition.Investition
    sensor_mapping_for_inv: dict,  # {"felder": {feld: {strategie, sensor_id, ...}}, "live": {...}}
) -> list[KomponentenBeitrag]:
    """Pro Investitions-Typ die korrekte Auswahl/Aufteilung — exakte Spec
    aus Snapshot-Variante übernehmen:
    - pv-module / balkonkraftwerk: pv_erzeugung_kwh
    - speicher: ladung_kwh (+), entladung_kwh (-); ladung_netz_kwh NICHT
    - waermepumpe: bei getrennte_strommessung strom_heizen+strom_warmwasser,
      sonst stromverbrauch_kwh. Niemals heizenergie/warmwasser/Counter.
    - wallbox: ladung_kwh only
    - e-auto: ladung_kwh ODER Fallback verbrauch_kwh; SKIP wenn parent_investition_id
    - sonstiges: primary (kategorie-abhängig) ODER Fallback secondary, immer +1
    Felder ohne strategie="sensor" oder ohne sensor_id werden übersprungen.
    """
```

**Anforderung:** Diese Funktion ist die *einzige* Stelle, wo die Per-Typ-Logik lebt. Beide Aggregator-Varianten konsumieren sie.

### Phase 2: Beide Aggregatoren auf den Helper umstellen

**`backend/services/snapshot/aggregator.py::get_komponenten_tageskwh`** (Snapshot-Variante):
- Behalten: die innere `_diff(sensor_key, sensor_id)`-Mechanik (Snapshot-DB + Self-Heal).
- Ersetzen: die Per-Typ-`if/elif`-Kaskade durch `for beitrag in investition_beitraege(inv, inv_data):` mit `_diff(beitrag.feld, ...)` und `result[beitrag.target_key] += beitrag.vorzeichen * delta`.
- E-Auto-Either-Or-Fallback: muss im Helper als zwei Beiträge mit Markierung ausgedrückt werden ODER der Helper bekommt eine `delta_lookup`-Callback und entscheidet selber. Variante A: Helper gibt `ladung_kwh` zurück, Aggregator versucht es; bei None → erneuter Helper-Aufruf mit `fallback=True` der `verbrauch_kwh` liefert. Variante B: Aggregator bekommt eine Liste `[primary_beitrag, fallback_beitrag]` und entscheidet. **Variante B ist sauberer**, weil die ganze Logik im Helper kapselt.

Vorschlag für Either-Or-Repräsentation:

```python
@dataclass(frozen=True)
class KomponentenBeitrag:
    feld: str
    target_key: str
    vorzeichen: int
    fallback_gruppe: Optional[str] = None  # "eauto_1" für Either-Or-Gruppe

# E-Auto: zwei Beiträge mit derselben fallback_gruppe — Aggregator nimmt
# nur den ersten der ein Delta != None liefert.
```

**`backend/services/snapshot/lts_aggregator.py::get_komponenten_tageskwh_lts`** (LTS-Variante):
- Behalten: die `ha_svc.get_hourly_kwh_deltas_for_day(sensor_ids, datum)`-Mechanik.
- Ersetzen: die generische `for feld, config in felder.items()`-Schleife durch dieselbe Helper-basierte Logik.

**Akzeptanz:** Beide Funktionen sind danach im Wesentlichen identisch, unterscheiden sich nur darin, wie sie das Tages-Delta pro Sensor holen.

### Phase 3: Parametrisierter Symmetrie-Test

**Datei (neu):** `eedc/backend/tests/test_aggregator_symmetrie.py`

Pytest-Parametrisierung über alle Investitionstyp-Konstellationen:

```python
@pytest.mark.parametrize("anlagen_setup", [
    "wp_strom_only",             # nur stromverbrauch
    "wp_strom_plus_thermisch",   # detLAN-Klasse
    "wp_getrennte_strommessung", # strom_heizen + strom_warmwasser
    "wp_mit_counter",            # + wp_starts_anzahl + wp_betriebsstunden
    "speicher_simple",           # nur ladung + entladung
    "speicher_arbitrage",        # + ladung_netz_kwh (Bug-Class)
    "wallbox_simple",            # nur ladung
    "wallbox_split",             # ladung + ladung_pv + ladung_netz (Gernot-Klasse)
    "eauto_ohne_wallbox",        # ladung_kwh / verbrauch_kwh
    "eauto_mit_split",           # + ladung_pv + ladung_netz
    "eauto_mit_parent_wallbox",  # parent_investition_id → skip
    "sonstiges_verbraucher_doppelt", # erzeugung + verbrauch beide
    # ... volle Permutation
])
async def test_snapshot_und_lts_liefern_identische_komponenten_kwh(
    anlagen_setup, db, fixed_synthetic_sensor_data
):
    """Für jeden Mapping-Setup synthetische Sensor-Daten in DB
    (sensor_snapshots + statistics-Mock); beide Aggregatoren werden
    gerufen; Ergebnis-Dicts müssen identisch sein."""
    ...
```

**Akzeptanz:** Symmetrie-Test grün für ALLE Permutationen. Das ist der strukturelle Schutz vor künftigen Asymmetrien.

### Phase 4: Erweiterung der Invariante

**Datei:** `eedc/backend/core/berechnungen/invarianten.py::pruefe_tep_tz_konsistenz`

Aktuell prüft sie nur `Σ TagesEnergieProfil.pv_kw == Σ komponenten_kwh[pv_*, bkw_*]`. Erweitern auf:
- `Σ TEP.verbrauch_kw vs Σ komp_kwh[waermepumpe_*, wallbox_*, eauto_*]` (Hausverbrauch-Komponenten)
- `Σ TEP.batterie_kw vs Σ komp_kwh[batterie_*]` (Speicher-Netto)
- `Σ TEP.einspeisung_kw vs komp_kwh[einspeisung]`
- `Σ TEP.netzbezug_kw vs komp_kwh[netzbezug]`

Pro Kategorie eine eigene KonsistenzBericht-Zeile. Bei Verletzung Log-Warning (wie heute) — Daten-Checker zeigt sie zusätzlich (siehe Phase 6).

**Akzeptanz:** wenn jemand morgen eine neue Asymmetrie einbaut, ploppt sie als Drift in der Invariante auf.

### Phase 5: Historische Datenbereinigung

**Strategie:** beim ersten Backend-Start nach v3.33.0-Update läuft eine **idempotente Daten-Migration** über `_run_data_migrations()` in `backend/core/database.py`.

**Migration-Logik:**

```python
# Datei: backend/services/migrations/migrate_v3_33_0_lts_komponenten_kwh.py

VERSION_BUG_EINGEFUEHRT = date(2026, 5, 16)   # v3.31.0
VERSION_BUG_BEHOBEN = date(...)                # v3.33.0-Release-Datum

async def migrate_lts_komponenten_kwh_bug(session):
    """Reaggregiert alle Tage zwischen 2026-05-16 und v3.33.0-Update für jede
    HA-Add-on-Anlage. Idempotent über migrations-Tabelle.

    Voraussetzung: get_komponenten_tageskwh_lts ist gefixt (Phase 1-3).
    Diese Migration ruft aggregate_day pro Tag — da landet nun der
    korrekte Wert in komponenten_kwh.

    Performance: max ~250 Tage × N Anlagen, pro Tag ~1-2s.
    Per-Tag-Commit (siehe #291-Fix) hält die DB-Locks kurz.
    Anlagen ohne HA-LTS-Statistics werden übersprungen.
    """
    anlagen = await session.execute(select(Anlage))
    for anlage in anlagen.scalars().all():
        if not anlage.sensor_mapping:
            continue  # nicht-konfigurierte Anlagen überspringen
        await backfill_range(
            anlage,
            von=VERSION_BUG_EINGEFUEHRT,
            bis=date.today() - timedelta(days=1),
            db=session,
        )
```

**Idempotenz:** Über die `migrations`-Tabelle wie schon `etappe_3c_p2_counter_hourly_backward` usw. — läuft genau einmal pro Installation.

**User-Sichtbarkeit:** beim ersten Start nach Update steht im Add-on-Log eine deutliche Zeile `[migration] LTS-komponenten_kwh-Drift-Korrektur: {n} Tage neu aggregiert für Anlage {id}`. Plus ein einmaliger persistenter HA-Hinweis (über `persistent_notification.create`) der die Migration anzeigt — sodass der Anwender weiß, dass seine Werte sich geändert haben können.

**Akzeptanz:** nach v3.33.0-Update-Boot sind alle historischen TZ.komponenten_kwh-Werte für betroffene Anlagen korrekt. Für Gernots Wallbox: 23.24 → 14.0 für den 22.5.

### Phase 6: Daten-Checker-Diagnose-Kategorie (optional)

**Datei:** `eedc/backend/services/daten_checker.py`

Neue Diagnose-Kategorie „KOMPONENTEN_DRIFT" die für jeden Tag der letzten 7 Tage die `pruefe_tep_tz_konsistenz`-Erweiterte-Invariante prüft und bei Drift einen Eintrag liefert mit Reparatur-Link auf `reaggregate_day`.

**Akzeptanz:** Drift wird im Daten-Checker sichtbar, anstatt nur als Log-Warning. Diagnose-Pfad-Stärkung.

---

## Concrete Verification — Gernots Anlage am 22.5.2026

Diese Verifikation wurde in der Diagnose-Session durchgeführt — die nächste Session kann sie als Sanity-Check nach dem Fix wiederholen.

**Anlage Winterborn (id=1) — Wallbox Carport (Inv 2):**

| Quelle | Wert |
|---|---|
| HA `sensor.sma_zahlerstand_wallbox` Δ über 22.5. (ladung_kwh) | 5445 − 5431 = **14 kWh** |
| HA `sensor.evcc_helper_pv_charged_kwh` Δ (ladung_pv_kwh) | 1981.32 − 1972.08 = 9.24 kWh |
| **LTS-Bug summiert beide** | 14 + 9.24 = **23.24 kWh** |
| **TZ.komponenten_kwh.wallbox_2 vor Fix** | **23.24 kWh** (verifiziert über `/api/energie-profil/1/tage?von=2026-05-20&bis=2026-05-23`) |
| **Erwartet nach Fix** | **14.0 kWh** |

**E-Auto Smart #1 (Inv 1)** am 22.5.: `eauto_1 = 49.0 kWh` vor Fix. Sensor `evcc_cstotal_smart_1_charged_energy` für `verbrauch_kwh` ist seit 23.5. 12:40 unavailable — Quantifizierung der Soll-Wert-Erwartung verlangt zusätzliche Recherche. Nach Fix sollte hier Snapshot-Variante-Logik gelten: `ladung_kwh` (nicht gemappt) → Fallback `verbrauch_kwh` = der reine evcc-Total-Delta für diesen Tag, vermutlich deutlich kleiner als 49.

**Aufruf zur Re-Verifikation nach Fix:**

```bash
# Reaggregate 22.5. manuell (oder Migration abwarten)
curl -X POST "http://10.100.1.13:8099/api/energie-profil/1/reaggregate-tag?datum=2026-05-22&mit_resnap=true"

# Werte prüfen
curl -s "http://10.100.1.13:8099/api/energie-profil/1/tage?von=2026-05-22&bis=2026-05-22" | python3 -m json.tool
```

Erwartet: `wallbox_2: 14.0`, `eauto_1` deutlich niedriger als 49.0.

---

## Schritt-für-Schritt-Plan für die nächste Session

> Reihenfolge ist wichtig: erst Helper + Symmetrie-Test → dann Aggregatoren umstellen → dann Invariante → dann Migration. Jede Phase committen vor der nächsten.

### Schritt 1: Helper-Modul anlegen

1. `eedc/backend/services/snapshot/komponenten_beitraege.py` erstellen mit `KomponentenBeitrag`-Dataclass + `basis_beitraege()` + `investition_beitraege()`.
2. Per-Typ-Logik exakt aus [`aggregator.py:444-516`](../../eedc/backend/services/snapshot/aggregator.py#L444-L516) übernehmen. **Quelle der Wahrheit ist die Snapshot-Variante — sie ist semantisch korrekt.**
3. Unit-Tests für den Helper: pro Typ + Edge-Cases (getrennte_strommessung, parent_investition_id, sonstiges-Erzeuger/Verbraucher).
4. Commit: „refactor(aggregator): Per-Typ-Komponenten-Beitrag-Logik in geteilten Helper extrahieren".

### Schritt 2: Symmetrie-Test schreiben (rot)

1. `eedc/backend/tests/test_aggregator_symmetrie.py` erstellen mit der Parametrisierung aus „Phase 3" oben.
2. Test-Helper für synthetische Sensor-Daten:
   - Für Snapshot-Variante: in `sensor_snapshots`-Tabelle Boundary-Snapshots schreiben
   - Für LTS-Variante: `ha_statistics_service.get_hourly_kwh_deltas_for_day` mocken
   - Beide bekommen dieselben „echten" stündlichen Deltas → identische Tages-Σ erwartet
3. Erwartung: Test schlägt für alle AKUT-Typen fehl, bestätigt damit den Bug-Scope.
4. Commit noch nicht — erst Schritt 3.

### Schritt 3: Aggregatoren auf Helper umstellen

1. `get_komponenten_tageskwh` (Snapshot-Variante) auf Helper umstellen. Verhalten sollte identisch bleiben — bestehende Tests in `test_lts_aggregator_konsistenz.py` und der neue Symmetrie-Test für Snapshot-Seite müssen grün bleiben.
2. `get_komponenten_tageskwh_lts` (LTS-Variante) auf Helper umstellen. Jetzt sollten **alle** Symmetrie-Test-Parametrisierungen grün werden.
3. Commit: „fix(lts-aggregator): Per-Typ-Filter analog Snapshot-Variante — Drift seit v3.31.0 (#290)".

### Schritt 4: Invariante erweitern + Test

1. `pruefe_tep_tz_konsistenz` in `core/berechnungen/invarianten.py` erweitern auf alle 4 Kategorien (PV/Verbrauch/Batterie/Basis).
2. Existierende Aufrufstellen prüfen (`aggregate_day`, ggf. Daten-Checker) — schreiben jetzt mehr Konsistenz-Berichte.
3. Tests: Drift-Szenarien je Kategorie → Bericht erwartet.
4. Commit: „feat(invariante): TEP↔TZ-Konsistenz auf alle Komponenten-Kategorien".

### Schritt 5: Historische Migration

1. `eedc/backend/services/migrations/migrate_v3_33_0_lts_komponenten_kwh.py` erstellen (Code-Skizze in Phase 5 oben).
2. In `backend/core/database.py::_run_data_migrations()` registrieren mit `_apply_once("v3_33_0_lts_komponenten_kwh_bereinigung", migrate_lts_komponenten_kwh_bug)`.
3. Persistente HA-Notification beim ersten Lauf.
4. **Wichtig:** Migration muss **nach** dem LTS-Aggregator-Fix laufen, sonst reaggregiert sie mit dem Bug. Reihenfolge in `_run_data_migrations` korrekt setzen.
5. Test: End-to-End auf Test-DB mit bekanntem alten Drift-Wert → Migration läuft → neuer Wert ist korrekt.
6. Commit: „feat(migration): historische LTS-Aggregator-Drift in komponenten_kwh bereinigen (#290)".

### Schritt 6: Daten-Checker-Erweiterung (optional)

1. Neue Diagnose-Kategorie `KOMPONENTEN_DRIFT` in `daten_checker.py` — pro Tag der letzten 7 Tage die erweiterte Invariante prüfen.
2. Bei Drift: Eintrag mit `action_kind="reaggregate_day"` analog der bestehenden IST-Lücke-Logik.
3. Commit: „feat(daten-checker): Komponenten-Drift-Kategorie sichtbar machen".

### Schritt 7: CHANGELOG + WAS-IST-NEU + Release

1. **CHANGELOG-Eintrag** für v3.33.0 mit klarer Beschreibung:
   - „Korrigiert: Per-Typ-Filter im LTS-Aggregator (seit v3.31.0 fehlerhaft). Betroffen waren HA-Add-on-Anlagen mit Multi-Sensor-Mappings für Wärmepumpe (thermische Sensoren), Speicher (Arbitrage), Wallbox (PV-/Netz-Split), E-Auto (Multi-Sensor) und Sonstiges (Hybrid)."
   - „Migration: historische `TagesZusammenfassung.komponenten_kwh`-Werte vom 16.5.–{Release-Datum} werden beim ersten Start nach Update automatisch reaggregiert."
2. **WAS-IST-NEU.md** mit anwenderfreundlicher Fassung.
3. **Tester benachrichtigen**: detLAN (#290) — Bug C+E (Punkt 3/4 aus seinem Bericht) sind damit auf Wurzel-Ebene gelöst. Schwippser-Hinweis prüfen (Zendure SolarFlow mit Arbitrage = ggf. Speicher-Drift-betroffen).
4. Release via `./scripts/release.sh 3.33.0`.

---

## Akzeptanzkriterien (Gesamt)

1. **Symmetrie-Test** grün für alle Per-Typ-Permutationen.
2. **Bestehende Suite** (479+ Tests) grün.
3. **Gernots Wallbox-22.5.-Verifikation**: nach Fix + Migration zeigt `/api/energie-profil/1/tage` für 22.5.2026 `wallbox_2 = 14.0` statt `23.24`.
4. **Migration idempotent**: zweiter Start nach Update macht nichts.
5. **Invariante**: bei künstlich eingebauter Drift wird der Bericht `konsistent=False`.
6. **Persistente HA-Notification** beim ersten Update-Boot sichtbar.

---

## Was NICHT in diesen Fix gehört

- **API-Vertrags-Tests** für die Orchestrator-Wrapper (Lehre aus Bug D `stunden_mit_messdaten`) → eigenes Thema, eigenes Päckchen.
- **Refactor von `live_tagesverlauf_service`** auf den geteilten Helper → wäre konsequent, aber dort sind die Keys teilweise unterschiedlich (z.B. `waermepumpe_<id>_heizen` Suffix). Anderes Konzept, eigene Session.
- **WP-Wärme-Output-Spalte im Tage-Tab** (detLANs separater Feature-Wunsch) — gehört in den Komponenten-Hub aus IA v4.0.0, nicht in diese Bereinigung.

---

## Memory-Updates für die nächste Session

Nach Abschluss bitte folgende Memory-Updates in `/home/gernot/.claude/projects/-home-gernot-claude-eedc-homeassistant/memory/`:

- **Neuer Eintrag** `feedback_aggregator_symmetrie.md` (type=feedback): „Bei zwei parallelen Implementierungen derselben Aggregations-Logik müssen Symmetrie-Tests existieren. Lektion: LTS-Aggregator-Bug 16.5.–v3.33.0 entstand weil generische Schleife statt der Snapshot-Per-Typ-Whitelist gebaut wurde, und kein Test beide Varianten gegeneinander hielt."
- **Eintrag erweitern** `feedback_aggregations_drift.md`: ergänze diesen Fall um die Liste der Drift-Klassen (LTS hatte 5 betroffene Typen, jetzt 6+ historische Vorfälle).
- **Eintrag aktualisieren** `MEMORY.md` Projektphase-Eintrag mit v3.33.0-Release-Hinweis.

---

## Kontakt-Tester-Hinweise

| User | Ggf. betroffen, weil | Re-Test nach Release |
|---|---|---|
| **detLAN** (#290) | WP-Mapping mit thermischen Sensoren + jetzt Betriebsstunden | „Tag neu aggregieren" 21.5. + 22.5. + heute prüfen — Wärmepumpe-Spalte sollte jetzt nur noch Strom zeigen (~3-6 kWh statt 30+) |
| **Schwippser** | Zendure SolarFlow mit Arbitrage → ggf. `ladung_netz_kwh` gemappt | Bei nächster Forum-Aktion erwähnen |
| **Gernot** (eigene Anlage) | Wallbox + E-Auto mit Multi-Sensor-Mapping (verifiziert) | nach Migration: 22.5. Wallbox = 14 kWh, heute Wallbox-Spalte sanity-check |
| **alle HA-Add-on-Anwender mit aktuellen WPs** | Falls jemand thermische Sensoren mappt | im Release-Hinweis transparent kommunizieren |

---

*Erstellt 2026-05-24 von Claude in Diagnose-Session mit Gernot. Die Diagnose-Schritte (Code-Review, HA-Sensor-Verifikation, TZ-Werte-Auslesen über eedc-API) sind nachvollzogen und dokumentiert; die nächste Session braucht sie nicht zu wiederholen, sondern kann direkt mit Schritt 1 der Implementierung anfangen.*
