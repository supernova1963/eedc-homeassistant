"""
Wächter: `ist_zaehler_differenz_feld` — wer darf aus HA-LTS gelesen werden?

Die Monatswert-Pfade aus HA (Monatsabschluss-Vorschläge, Statistik-Import)
rechnen ausnahmslos `MAX(sum) − MIN(sum)` mit Fallback über `state`. Für einen
Zählerstand ist das richtig, für alles andere Unsinn — bei einem Preis-Sensor
käme die Monats-Spreizung heraus, und sie landete beim Import persistent in
`verbrauch_daten` (Forum simon42 #89667/54).

Das Prädikat trägt die Grenze. Zwei Richtungen sind zu wächten, und beide sind
schon einmal schiefgegangen:

1. **Zu breit** — der ursprüngliche Zustand: alles wurde gelesen.
2. **Zu eng** — beim Bau dieses Filters wäre fast der PV-Sammelzähler
   herausgefallen: `pv_gesamt` ist ein reiner Mapping-Schlüssel und steht in
   keiner Feld-Registry, `FELD_EINHEITEN` kennt ihn nicht. Ein zu enger Filter
   meldet nichts — er liefert nur still weniger Daten.
"""

from __future__ import annotations

from backend.core.field_definitions import ist_zaehler_differenz_feld
from backend.services.datenquellen_mapping_sync import BASIS_ENERGY_FELD, BASIS_PREIS_FELD
from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    KUMULATIVE_ZAEHLER_FELDER,
)


def test_alle_kumulativen_felder_sind_lesbar():
    """Kein Zähler-Feld darf still aus den HA-Lesepfaden fallen."""
    zaehler = {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
    counter = {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
    fehlend = sorted(f for f in zaehler | counter if not ist_zaehler_differenz_feld(f))
    assert fehlend == [], (
        f"Zähler-Felder, die der HA-Import überspringen würde: {fehlend}"
    )


def test_basis_zaehler_bleiben_lesbar():
    """Die drei Basis-Mapping-Schlüssel — inklusive `pv_gesamt`, das in keiner
    Feld-Registry steht und deshalb der Kandidat für stillen Verlust ist."""
    fehlend = sorted(f for f in BASIS_ENERGY_FELD.values() if not ist_zaehler_differenz_feld(f))
    assert fehlend == [], f"Basis-Zähler ohne Lese-Deckung: {fehlend}"


def test_preis_und_kosten_felder_bleiben_draussen():
    """Die Gegenrichtung: was keine Zählerdifferenz ist, wird nicht gelesen."""
    for feld in (
        *BASIS_PREIS_FELD.values(),   # basis["strompreis"] — ct/kWh
        "speicher_ladepreis_cent",    # ct/kWh (der gemeldete Fall)
        "ladung_extern_euro",         # € — Handeingabe, kein Zähler
        "warmwasser_temperatur_c",    # °C
        "netzbezug_durchschnittspreis_cent",  # ct/kWh
        "kraftstoffpreis_euro",       # €/L
    ):
        assert not ist_zaehler_differenz_feld(feld), feld


def test_zaehler_ohne_energie_einheit_bleiben_drin():
    """km und Anzahl sind Zähler, auch ohne kWh — ihre Differenz ist der
    Monatswert (gefahrene km, Anzahl Ladevorgänge)."""
    for feld in ("km_gefahren", "ladevorgaenge", "wp_starts_anzahl", "wp_betriebsstunden"):
        assert ist_zaehler_differenz_feld(feld), feld
