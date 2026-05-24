# Folge-Ticket: Hourly-Pfad `_categorize_counter` E-Auto-Doppelmapping

> Entdeckt während v3.33.0-Diagnose (Issue #290 LTS-Aggregator-Drift).
> Keine Anwenderbeschwerde — latenter Bug.
> Eigene Session, eigenes Päckchen.

## Symptom

Wenn ein Anwender für eine E-Auto-Investition sowohl `verbrauch_kwh` als auch `ladung_kwh` mappt, summiert der hourly-Aggregator (`get_hourly_kwh_by_category` und `get_hourly_kwh_by_category_lts`) beide Sensoren pro Stunde unter der Kategorie `"verbrauch_eauto"` auf. Daraus resultieren TEP-Werte (`wallbox_kw` Spalte enthält wp/wallbox/eauto kategorisiert), die doppelt so hoch sind wie korrekt.

## Wurzelursache

[backend/services/snapshot/keys.py::_categorize_counter](../../eedc/backend/services/snapshot/keys.py) kategorisiert für `inv_typ == "e-auto"` BEIDE Felder zur selben Kategorie:

```python
if inv_typ == "e-auto" and feld in ("verbrauch_kwh", "ladung_kwh"):
    return "verbrauch_eauto"
```

Im hourly-Pfad wird dann für jede Stunde über alle Einträge mit dieser Kategorie summiert — Doppelmapping = Doppelzählung. Der Daily-Pfad (seit v3.33.0 über [komponenten_beitraege.py](../../eedc/backend/services/snapshot/komponenten_beitraege.py)) macht Either-Or und ist korrekt.

## Manifestation

Die v3.33.0-Invariante `pruefe_tep_tz_komponenten_konsistenz` würde bei so einer Anlage anschlagen (Σ TEP.wallbox_kw zu hoch gegen Σ komp_kwh[wallbox_*, eauto_*]). Aktuell aber rein latent, weil kein Anwenderbericht vorliegt.

Außerdem fehlt im hourly-Pfad der `parent_investition_id`-Skip für E-Autos, die von einer Wallbox gemessen werden — analog zum Daily-Pfad. Wenn beide vorhanden, addiert die hourly-Aggregation jetzt Wallbox-ladung_kwh und E-Auto-ladung_kwh zum selben "verbrauch_eauto"-Bucket.

## Fix-Vorschlag

`_categorize_counter` kann nicht ohne Weiteres Either-Or machen, weil sie keinen Zugriff auf den gesamten Mapping-State hat (sie wird pro Feld aufgerufen). Zwei Optionen:

1. **Helper-Variante:** Neuen Helper analog zum Daily-Pfad — `_categorize_counter_with_mapping(felder_dict, inv, feld) -> Optional[str]`. Dann kann er entscheiden, dass `verbrauch_kwh` ignoriert wird, wenn `ladung_kwh` auch gemappt ist. Aufrufer (hourly-Aggregatoren) müssen umgestellt werden.

2. **Mapping-normalisieren:** Vor dem hourly-Pfad das `sensor_mapping`-Dict einmalig filtern — nur die für die Per-Typ-Logik korrekten Felder behalten. Daily- und Hourly-Pfad konsumieren dann beide das normalisierte Mapping.

**Variante 2 ist sauberer** — der normalisierende Schritt nutzt den Helper aus `komponenten_beitraege.py`, alle Aggregatoren laufen über dieselbe Pre-Filter-Schicht.

## Akzeptanzkriterien

1. Symmetrie-Test analog zum Daily-Pfad: hourly-Σ über alle Stunden == daily-Σ pro Investition.
2. E-Auto-Doppelmapping liefert das richtige Tages-Σ (nur ladung_kwh).
3. E-Auto mit `parent_investition_id` taucht im hourly-Pfad nicht mehr als "verbrauch_eauto" auf.

## Bezug

- v3.33.0 (Issue #290) — Daily-Pfad-Fix in [komponenten_beitraege.py](../../eedc/backend/services/snapshot/komponenten_beitraege.py)
- Memory: [[feedback_aggregator_symmetrie]] — Symmetrie-Test-Pattern
