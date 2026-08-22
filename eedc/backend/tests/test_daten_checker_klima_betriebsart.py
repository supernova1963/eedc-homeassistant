"""D2 — der Daten-Checker und die gemessenen Betriebsarten (#263, v4.0.24).

Zwei Befunde, beide an der Zielgruppe von v4.0.24:

**F-60** — ``_check_klima_modus_sensor`` kannte nur den *abgeleiteten* Weg zur
Heiz-/Kühl-Aufteilung (die ``climate``-Entität) und meldete deshalb
„Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen" auch
dort, wo der Verbrauch je Betriebsart **gemessen** ankommt. Beide Halbsätze
waren falsch, und der zweite wog schwerer: ``modus_strom_zeile`` entscheidet
*gemessen schlägt abgeleitet, ganz oder gar nicht je Zeile* — wer dem Rat der
Meldung folgte, erzeugte einen Split, den eedc anschließend verwirft.

**N-310** — ein Feld-Key kann eine Innengeräte-Adresse tragen
(``betriebsart_strom_kuehlen_kwh-3``). Beide Sensor-Prüfungen schlugen den
**rohen** Key nach; ohne Auflösung fällt der Sensor aus dem Energie-Filter und
wird nie geprüft, das Label zeigt den Rohschlüssel. Bei
``_check_sensor_mapping_einheit`` reicht das bis in die **#674-ERROR**-Klasse,
weil ``leistung_w`` es je Innengerät gibt.
"""

from datetime import date

import pytest

from backend.core.betriebsmodus import (
    BETRIEBSART_STROM_FELD,
    HEIZEN,
    KUEHLEN,
    ist_betriebsart_strom_feld,
)
from backend.core.field_definitions import feld_je_innengeraet
from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.services.daten_checker import DatenChecker

pytestmark = pytest.mark.asyncio

#: Eine Klimaanlage mit drei Innengeräten — dieselbe Form wie in
#: `test_263_innengeraete.py`, damit beide Proben dasselbe Gerät meinen.
MIT_LISTE = {
    "wp_art": "luft_luft",
    "innengeraete": [
        {"id": 1, "name": "Büro"},
        {"id": 2, "name": "Wohnzimmer"},
    ],
}


async def _anlage_mit_klima(db, *, parameter=None, mapping=None):
    anlage = Anlage(
        anlagenname="Klima-Probe", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=parameter or {"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()
    if mapping is not None:
        anlage.sensor_mapping = mapping(inv.id)
    await db.commit()
    return anlage, inv


async def _modus_meldungen(db, anlage):
    return await DatenChecker(db)._check_klima_modus_sensor(anlage)


# ═══ F-60 — beide Wege zur Aufteilung ═══════════════════════════════════════

async def test_ohne_jede_aufteilung_bleibt_der_hinweis_wortgleich(db):
    """Die Deckung darf nicht verloren gehen — der Ursprungsfall steht weiter.

    Ohne diese Probe könnte der Fix die Meldung schlicht abschalten und alle
    anderen Proben blieben grün.
    """
    anlage, _ = await _anlage_mit_klima(db)
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.schwere == "info"
    assert "Betriebsmodus nicht zugeordnet" in e.meldung
    assert "Heiz- und Kühlstrom bleiben zusammen" in e.meldung


async def test_zaehler_am_geraet_zugeordnet_beendet_die_falschmeldung(db):
    """F-60, Zweig 1 — der Weg, den die v4.0.24-Zielgruppe geht."""
    anlage, _ = await _anlage_mit_klima(db, mapping=lambda iid: {
        "investitionen": {str(iid): {"felder": {
            BETRIEBSART_STROM_FELD[HEIZEN]: {
                "strategie": "sensor", "sensor_id": "sensor.klima_heizen",
            },
        }}},
    })
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "ok"
    # Die Herkunft gehört in den Text: sonst sieht niemand, dass eedc hier
    # ABLIEST statt zu rechnen.
    assert "gemessen" in ergebnisse[0].details


async def test_zaehler_je_innengeraet_beendet_die_falschmeldung(db):
    """F-60, Zweig 1 + Suffix — `betriebsart_strom_kuehlen_kwh-2`.

    Ohne die Basis-Key-Auflösung im Prüfer wäre dieses Gerät weiterhin „ohne
    Aufteilung", obwohl beide Innengeräte zugeordnet sind.
    """
    feld = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 2)
    anlage, _ = await _anlage_mit_klima(db, parameter=MIT_LISTE, mapping=lambda iid: {
        "investitionen": {str(iid): {"felder": {
            feld: {"strategie": "sensor", "sensor_id": "sensor.wohnzimmer_kuehlen"},
        }}},
    })
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1, [e.meldung for e in ergebnisse]
    assert ergebnisse[0].schwere == "ok"


async def test_quelle_ueber_mqtt_beendet_die_falschmeldung(db):
    """F-60, Zweig 1 — die feld-zentrische Zuordnung.

    Die Datenquellen-Fläche legt MQTT- und Connector-Quellen unter `quellen` ab,
    **nicht** unter `felder`. Ein Prüfer, der nur `felder` liest, ließe die
    Falschmeldung für jeden MQTT-Nutzer stehen.
    """
    anlage, _ = await _anlage_mit_klima(db, mapping=lambda iid: {
        "quellen": {
            f"inv_energy_{iid}_{BETRIEBSART_STROM_FELD[HEIZEN]}": {
                "quelle": "mqtt_inbound_standard", "entity_id": None,
            },
        },
    })
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "ok"


async def test_quelle_ausdruecklich_keine_ist_keine_zuordnung(db):
    """„Keine" ist eine Absage, kein Weg — sonst schaltete sie den Hinweis ab.

    Die Gegenprobe zur Probe darüber: derselbe Eintrag, andere Quelle.
    """
    anlage, _ = await _anlage_mit_klima(db, mapping=lambda iid: {
        "quellen": {
            f"inv_energy_{iid}_{BETRIEBSART_STROM_FELD[HEIZEN]}": {
                "quelle": "keine", "entity_id": None,
            },
        },
    })
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "info"


async def test_gemessene_monatszeile_ohne_jede_zuordnung_beendet_die_meldung(db):
    """F-60, Zweig 2 — die von Hand gepflegte Zeile.

    Wer die vier Werte im Monatsabschluss einträgt, hat gar keine Zuordnung und
    trotzdem die Aufteilung. Zweig 1 allein ließe die Falschmeldung hier stehen.
    """
    anlage, inv = await _anlage_mit_klima(db)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2025, monat=6,
        verbrauch_daten={
            "stromverbrauch_kwh": 120.0,
            BETRIEBSART_STROM_FELD[KUEHLEN]: 90.0,
        },
    ))
    await db.commit()

    ergebnisse = await _modus_meldungen(db, anlage)
    assert len(ergebnisse) == 1, [e.meldung for e in ergebnisse]
    assert ergebnisse[0].schwere == "ok"


async def test_monatszeile_ohne_betriebsart_beendet_die_meldung_nicht(db):
    """Gegenprobe zu Zweig 2: eine Zeile allein reicht nicht.

    Ohne sie könnte der Fix auf „gibt es irgendeine Monatszeile?" hinauslaufen
    und diese Probe bliebe grün.
    """
    anlage, inv = await _anlage_mit_klima(db)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2025, monat=6,
        verbrauch_daten={"stromverbrauch_kwh": 120.0},
    ))
    await db.commit()

    ergebnisse = await _modus_meldungen(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "info"


async def test_der_abgeleitete_weg_traegt_weiter_und_sagt_es(db):
    """Die `climate`-Zuordnung bleibt ein gültiger Weg — mit eigener Herkunft."""
    anlage, _ = await _anlage_mit_klima(db, mapping=lambda iid: {
        "investitionen": {str(iid): {"live": {"betriebsmodus": "climate.klima"}}},
    })
    ergebnisse = await _modus_meldungen(db, anlage)

    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "ok"
    assert "Betriebsmodus" in ergebnisse[0].details or "gekühlt" in ergebnisse[0].details
    # Und ausdrücklich NICHT als gemessen ausgewiesen — es ist gerechnet.
    assert "gemessen" not in ergebnisse[0].details


async def test_der_namens_helfer_loest_das_innengeraete_suffix_auf():
    """`ist_betriebsart_strom_feld` ist die Zuordnungs-Frage, suffix-tolerant."""
    assert ist_betriebsart_strom_feld(BETRIEBSART_STROM_FELD[KUEHLEN])
    assert ist_betriebsart_strom_feld(
        feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3)
    )
    # Die Nutzenergie ist eine andere Größe und verdrängt keine Stromaufteilung.
    assert not ist_betriebsart_strom_feld("betriebsart_nutzenergie_kuehlen_kwh")
    assert not ist_betriebsart_strom_feld("stromverbrauch_kwh")
    assert not ist_betriebsart_strom_feld("betriebsmodus")


# ═══ N-310 — Innengeräte in den Sensor-Prüfungen ════════════════════════════
#
# ⚠ **Diese Proben rufen die PRÜFER**, nicht `FELD_EINHEITEN`. Ein erster
# Entwurf verglich hier nur Registry-Einträge — er wäre auch dann grün
# geblieben, wenn `sensoren.py` unverändert bliebe, und hätte damit genau die
# Aussage geschützt, die er widerlegen soll.


class _FakeHaStats:
    """HA-LTS-Doppel — Form übernommen aus `test_daten_checker_lts_summen_spalte`."""

    is_available = True

    def __init__(self, ohne_sum: set[str] | None = None):
        self._ohne_sum = ohne_sum or set()

    def filter_summen_faehige_sensor_ids(self, sids):
        return (
            [s for s in sids if s not in self._ohne_sum],
            [s for s in sids if s in self._ohne_sum],
            [],
        )


class _FakeHaState:
    def __init__(self, units):
        self._units = units

    async def get_sensor_units(self, entity_ids):
        return {e: self._units[e] for e in entity_ids if e in self._units}


async def _geladen(db, anlage_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def test_lts_pruefung_meldet_den_zaehler_eines_innengeraets(db, monkeypatch):
    """N-310 — vorher fiel dieser Sensor still aus dem Energie-Filter.

    Der Zähler eines Innengeräts hat kein `has_sum`; ohne Basis-Key-Auflösung
    prüfte ihn niemand, und der Anwender bekam ein grünes „alle kWh-Sensoren
    verfügbar", während Tages- und Stundenebene leer blieben.
    """
    import backend.services.ha_statistics_service as ha_mod

    feld = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3)
    anlage, _ = await _anlage_mit_klima(db, parameter=MIT_LISTE, mapping=lambda iid: {
        "investitionen": {str(iid): {"felder": {
            feld: {"strategie": "sensor", "sensor_id": "sensor.buero_kuehlen"},
        }}},
    })
    monkeypatch.setattr(
        ha_mod, "get_ha_statistics_service",
        lambda: _FakeHaStats(ohne_sum={"sensor.buero_kuehlen"}),
    )

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(
        await _geladen(db, anlage.id)
    )

    warnungen = [r for r in ergebnisse if r.schwere == "warning"]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    details = warnungen[0].details or ""
    assert "sensor.buero_kuehlen" in details
    # Und mit lesbarem Label statt Rohschlüssel — ein Roh-Key ist keine Auskunft.
    assert "Strom Kühlbetrieb" in details
    assert feld not in details


async def test_einheiten_pruefung_meldet_kwh_im_leistungsslot_eines_innengeraets(
    db, monkeypatch,
):
    """N-310 reicht bis in die #674-ERROR-Klasse.

    `leistung_w` gibt es je Innengerät. Ohne Auflösung fiel `leistung_w-1` aus
    der Prüfung — und mit ihm der Fall, in dem ein kWh-Zählerstand als
    Momentanleistung gelesen wird und den live gerechneten Hausverbrauch auf 0
    klemmt.
    """
    import backend.services.ha_state_service as hss

    feld = feld_je_innengeraet("leistung_w", 1)
    anlage, _ = await _anlage_mit_klima(db, parameter=MIT_LISTE, mapping=lambda iid: {
        "investitionen": {str(iid): {"live": {feld: "sensor.buero_zaehlerstand"}}},
    })
    monkeypatch.setattr(
        hss, "get_ha_state_service",
        lambda: _FakeHaState({"sensor.buero_zaehlerstand": "kWh"}),
    )

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_einheit(
        await _geladen(db, anlage.id)
    )

    fehler = [r for r in ergebnisse if r.schwere == "error"]
    assert len(fehler) == 1, [f"{r.schwere}: {r.meldung}" for r in ergebnisse]
    assert "Leistung" in fehler[0].meldung or "Leistung" in (fehler[0].details or "")


async def test_der_zustands_slot_bleibt_auch_nach_der_aufloesung_draussen(
    db, monkeypatch,
):
    """Gegenprobe: die Auflösung darf keinen Fehlalarm bauen.

    `betriebsmodus-1` löst zu `betriebsmodus` auf. Dessen Einheit ist leer, der
    Slot bleibt draußen — vorher war das nur ZUFÄLLIG richtig (der rohe Key
    stand in keiner Tabelle), jetzt trägt es die Regel aus `ZUSTAND_LIVE_FELDER`.
    Ohne diese Probe könnte die Auflösung eine `climate`-Entität in die
    Einheiten-Prüfung ziehen und dort dauerhaft ERROR melden.
    """
    import backend.services.ha_state_service as hss

    feld = feld_je_innengeraet("betriebsmodus", 1)
    anlage, _ = await _anlage_mit_klima(db, parameter=MIT_LISTE, mapping=lambda iid: {
        "investitionen": {str(iid): {"live": {feld: "climate.buero"}}},
    })
    monkeypatch.setattr(
        hss, "get_ha_state_service", lambda: _FakeHaState({"climate.buero": ""}),
    )

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_einheit(
        await _geladen(db, anlage.id)
    )
    assert ergebnisse == [], [f"{r.schwere}: {r.meldung}" for r in ergebnisse]
