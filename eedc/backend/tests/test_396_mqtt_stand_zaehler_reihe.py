"""#396 (gruaGit) — km-Zaehler und Ladevorgaenge bekommen ihre MQTT-Zaehlerreihe.

**Der gemeldete Fall.** gruaGit faehrt Standalone und fuettert alles per MQTT,
darunter den kumulativen km-Stand seines E-Autos. eedc bietet genau das als
Quelle an — der Feld-Hinweis wirbt woertlich mit dem „kumulativen km-Zaehler
(Auto-Integration/OBD)". Einen Monatsvorschlag bekam er trotzdem nie und trug
die gefahrenen Kilometer von Hand ein. Seine Frage: *„Waere es nicht moeglich
auch hier mitzuloggen und Monatsmengen zu erstellen?"*

**Die Ursache war eine Asymmetrie zwischen zwei Listen.**
`ist_zaehler_differenz_feld` fuehrt `km_gefahren` und `ladevorgaenge` als
Zaehlerdifferenz-Felder — eingeloest wurde das aber nur ueber HA, wo die
Statistik `MAX − MIN` direkt aus der Recorder-DB rechnet, ganz ohne Reihe. Ein
MQTT-Anwender hat keine Recorder-DB; bei ihm entsteht die Menge nur, wenn eedc
die Staende selbst mitschreibt. `_mqtt_key_to_sensor_key` gab fuer beide Felder
`None` zurueck, es entstand kein Snapshot, und `mqtt_monats_deltas` konnte
nichts differenzieren.

⛔ **Was hier NICHT zurueckgedreht wird, und das ist der Kern.** Der Ausschluss
war begruendet: Vorher landete gruaGits Tachostand **roh** im Monatsfeld — 13272
statt 1001 gefahrener Kilometer. Verboten ist das **rohe Durchreichen** eines
Standes, nicht die Reihe (F-66/N-335, P0). Die Invariante *ein Stand ist keine
Menge* gilt unveraendert und wird hier eigens geprueft: Der Vorschlag ist die
**Differenz**, nie der Stand.

⭐ **Die Anlage wird ueber den ECHTEN Weg hergestellt** (Lehre aus N-328/W-5):
`materialisiere_datenquellen` fuer die `quellen`-Ablage, `MqttEnergySnapshot`-
Zeilen wie der Cache-Schreiber sie anlegt, und der Produktions-Writer
`snapshot_anlage` fuer die `sensor_snapshots`. Wer die Zustaende von Hand
hinschreibt, prueft seine eigene Annahme.

⚠ **Feste Daten, kein gleitendes Fenster.** `mqtt_monats_deltas` bildet seinen
Zeitraum aus `jahr`/`monat` und fragt die Uhr nicht — ein abgeschlossener Monat
ist damit in jeder Zeitzone derselbe. Das ist die Lehre vom 28.08.2026, als eine
Probe mit festem Messtag gegen das gleitende 7-Tage-Fenster des Daten-Checkers
einen Tag nach ihrer Entstehung rot wurde.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.core.field_definitions import ist_zaehler_differenz_feld
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    materialisiere_datenquellen,
)
from backend.services.mqtt_energy_history_service import mqtt_monats_deltas
from backend.services.snapshot.keys import (
    MQTT_STAND_ZAEHLER_FELDER,
    _mqtt_key_to_sensor_key,
    extract_quellen_energy,
)
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories as f

#: Ein **abgeschlossener** Monat. `mqtt_monats_deltas` rechnet dann von
#: 01.06. 00:00 bis 01.07. 00:00 und ruehrt die Uhr nicht an.
JAHR, MONAT = 2026, 6
VON = datetime(JAHR, MONAT, 1)
BIS = datetime(JAHR, MONAT + 1, 1)


async def _mqtt_anlage(db, staende: dict[str, tuple[float, float]]):
    """Standalone-Anlage mit E-Auto und Wallbox, ausschliesslich per MQTT.

    Args:
        staende: ``{mqtt_key: (stand_am_monatsanfang, stand_am_monatsende)}``.
            Die Keys traegt der Aufrufer, damit dieselbe Anlage fuer den
            Positiv-, den Negativ- und den Reset-Fall dient.
    """
    anlage = await f.anlage(db, anlagenname="Standalone")
    auto = await f.investition(db, anlage.id, "e-auto", bezeichnung="ID.3")
    wb = await f.investition(db, anlage.id, "wallbox", bezeichnung="go-e Charger")
    await db.commit()

    # (1) Echter Weg zur `quellen`-Ablage.
    await materialisiere_datenquellen(db)
    await db.commit()
    await db.refresh(anlage)

    # (2) Echter Weg zu den Staenden: MqttEnergySnapshot-Zeilen.
    aufgeloest = {
        key.format(auto=auto.id, wb=wb.id): werte for key, werte in staende.items()
    }
    for key, (start, ende) in aufgeloest.items():
        for ts, wert in ((VON, start), (BIS, ende)):
            db.add(MqttEnergySnapshot(
                anlage_id=anlage.id, timestamp=ts, energy_key=key, value_kwh=wert,
            ))
    await db.commit()

    # (3) Echter Weg zu den SensorSnapshots: der Produktions-Writer.
    for ts in (VON, BIS):
        await snapshot_anlage(db, anlage, zeitpunkt=ts)
    await db.commit()

    return anlage, auto, wb, list(aufgeloest.keys())


async def _monatsmengen(db, anlage, keys: list[str]) -> dict[str, float]:
    return await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, keys,
        quellen_energy=extract_quellen_energy(anlage),
    )


# ─────────────────────────────────────────────────────────────────────────
# Der gemeldete Fall
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_km_stand_wird_zur_monatsmenge(db):
    """Der Tachostand ergibt die gefahrenen Kilometer — 1001, nicht 13272.

    Die beiden Zahlen sind die des Melders: Er sah 13272 im Monatsfeld, wo
    1001 hingehoerten.
    """
    anlage, auto, _wb, keys = await _mqtt_anlage(db, {
        "inv/{auto}/km_gefahren": (12271.0, 13272.0),
    })

    mengen = await _monatsmengen(db, anlage, keys)

    assert mengen[f"inv/{auto.id}/km_gefahren"] == 1001.0
    assert 13272.0 not in mengen.values(), "der STAND darf nie als Menge erscheinen"


@pytest.mark.asyncio
async def test_ladevorgaenge_bekommen_dieselbe_reihe(db):
    """`ladevorgaenge` ist dieselbe Bauform — kein Melder, trotzdem im Modell.

    Ein Anzahl-Zaehler der Wallbox ist wie der Tachostand ein kumulativer Stand
    ohne kWh-Semantik. Ihn wegzulassen hiesse, das Modell aus dem Fall eines
    einzelnen Melders abzuleiten.
    """
    anlage, _auto, wb, keys = await _mqtt_anlage(db, {
        "inv/{wb}/ladevorgaenge": (100.0, 112.0),
    })

    mengen = await _monatsmengen(db, anlage, keys)

    assert mengen[f"inv/{wb.id}/ladevorgaenge"] == 12.0


@pytest.mark.asyncio
async def test_fahrzeugwechsel_liefert_keinen_vorschlag(db):
    """Ein fallender Tachostand ist ein Zaehlertausch — dann gibt es KEINE Zahl.

    `reader.delta` verwirft negative Deltas. Ein Fahrzeugwechsel sieht genau so
    aus, und ein erfundener Wert waere hier schlimmer als gar keiner: Der
    Anwender traegt den Monat einmal von Hand ein statt eine falsche Zahl zu
    uebernehmen. **Kein Eintrag heisst „keine Aussage", nicht „null".**
    """
    anlage, auto, _wb, keys = await _mqtt_anlage(db, {
        "inv/{auto}/km_gefahren": (98000.0, 120.0),
    })

    mengen = await _monatsmengen(db, anlage, keys)

    assert f"inv/{auto.id}/km_gefahren" not in mengen


# ─────────────────────────────────────────────────────────────────────────
# Die Gegenrichtung: was KEINE Reihe bekommen darf
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preisfeld_bekommt_weiterhin_keine_reihe(db):
    """Ein Preis ist kein Zaehler — seine Differenz waere die Monats-Spreizung.

    Genau dieser Fehler schrieb einmal die Preis-Spanne als Ø Ladepreis in die
    Datenbank (Forum simon42 #89667/54). Die Erweiterung um die Stand-Zaehler
    darf ihn nicht wieder aufmachen.
    """
    anlage, _auto, wb, keys = await _mqtt_anlage(db, {
        "inv/{wb}/speicher_ladepreis_cent": (22.0, 31.0),
    })

    mengen = await _monatsmengen(db, anlage, keys)

    assert mengen == {}, "ein Preisfeld darf keinen Monatsvorschlag erzeugen"
    assert _mqtt_key_to_sensor_key(f"inv/{wb.id}/speicher_ladepreis_cent") is None


def test_soc_und_temperatur_bleiben_ohne_reihe():
    """Zustandsgroessen sind keine Zaehler — sie steigen nicht monoton."""
    assert _mqtt_key_to_sensor_key("inv/7/soc") is None
    assert _mqtt_key_to_sensor_key("inv/7/temperatur") is None


# ─────────────────────────────────────────────────────────────────────────
# Der Waechter: die Behauptung ueber zwei Listen
# ─────────────────────────────────────────────────────────────────────────

#: Zaehlerdifferenz-Felder, die bewusst KEINE MQTT-Reihe je Investition
#: brauchen — mit Grund, nicht als Auslassung.
_OHNE_MQTT_REIHE_JE_INVESTITION: dict[str, str] = {
    # Basis-Mapping-Schluessel des PV-Sammelzaehlers: anlagenweit, nicht je
    # Investition. Seine Reihe laeuft ueber `_MQTT_BASIS_KEYS`/`basis:pv_gesamt`.
    "pv_gesamt": "Basis-Zaehler der Anlage, eigener Weg ueber _MQTT_BASIS_KEYS",
}


def test_jedes_zaehlerdifferenz_feld_hat_einen_mqtt_weg():
    """Wer ein Feld als Zaehlerdifferenz-Feld fuehrt, schuldet ihm einen Weg.

    ⭐ **Das ist der Waechter fuer genau den Widerspruch, aus dem #396
    entstanden ist.** eedc fuehrte `km_gefahren` als Zaehlerdifferenz-Feld und
    warb im Feld-Hinweis mit dem OBD-Zaehler — eingeloest wurde es nur fuer
    HA-Anwender. Die Luecke war keine Entscheidung, sie war unbemerkt.

    Die Probe haelt die Beziehung zwischen zwei Listen fest, die in
    verschiedenen Dateien stehen und verschiedene Fragen beantworten. Wer
    kuenftig ein Feld zu `ist_zaehler_differenz_feld` hinzufuegt, entscheidet
    hier ausdruecklich: Reihe **oder** begruendete Ausnahme.
    """
    from backend.core.field_definitions import _ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT
    from backend.services.snapshot.keys import (
        KUMULATIVE_COUNTER_FELDER,
        KUMULATIVE_ZAEHLER_FELDER,
    )

    mit_reihe = (
        {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
        | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
        | MQTT_STAND_ZAEHLER_FELDER
    )

    ohne_weg = {
        feld for feld in _ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT
        if feld not in mit_reihe and feld not in _OHNE_MQTT_REIHE_JE_INVESTITION
    }

    assert not ohne_weg, (
        f"Zaehlerdifferenz-Felder ohne MQTT-Reihe und ohne begruendete Ausnahme: "
        f"{sorted(ohne_weg)} — entweder in MQTT_STAND_ZAEHLER_FELDER aufnehmen "
        f"oder in _OHNE_MQTT_REIHE_JE_INVESTITION mit Grund eintragen."
    )


def test_die_neuen_felder_sind_wirklich_zaehlerdifferenz_felder():
    """Gegenrichtung: nichts in der neuen Liste, das dort nicht hingehoert.

    Ein Feld in `MQTT_STAND_ZAEHLER_FELDER`, das eedc **nicht** als
    Zaehlerdifferenz-Feld fuehrt, waere die Behauptung, aus seinem Verlauf
    liesse sich eine Monatsmenge bilden — genau der Fehler, den der
    Preis-Sensor einmal ausgeloest hat.
    """
    for feld in MQTT_STAND_ZAEHLER_FELDER:
        assert ist_zaehler_differenz_feld(feld), (
            f"{feld!r} steht in MQTT_STAND_ZAEHLER_FELDER, gilt aber nicht als "
            f"Zaehlerdifferenz-Feld — aus seinem Verlauf entsteht keine Menge."
        )
