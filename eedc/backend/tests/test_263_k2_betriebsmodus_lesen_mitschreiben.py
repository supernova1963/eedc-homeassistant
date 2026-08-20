"""#263 K-2, S1+S2: den Betriebsmodus lesen und je Stunde mitschreiben.

Eine Split-Klimaanlage ist physikalisch eine Luft-Luft-Wärmepumpe: dasselbe
Gerät heizt im Winter und kühlt im Sommer, über **denselben** Stromzähler. eedc
sieht deshalb nur eine Jahreszahl „Stromverbrauch" — und **die Aufteilung ist
aus keinem vorhandenen Feld rekonstruierbar.** Sie entsteht nur, wenn der
Betriebsmodus zur Messzeit mitgeschrieben wird.

Diese Datei deckt die zwei Etappen ab, die das möglich machen:

* **S1 Lesen** — Kanon + Normalisierung (`core/betriebsmodus.py`), der
  Zustands-Lesepfad **neben** dem float-only-Bestandspfad
  (`ha_state_service.get_zustand_history`), das optionale Feld in der
  Zuordnungs-Fläche und der Daten-Checker-Hinweis.
* **S2 Mitschreiben** — `TagesEnergieProfil.betriebsmodus_je_wp`, gefüllt aus
  `_get_betriebsmodus_history`.

⚠ **Ehrlich zur Belegbarkeit:** Es gibt **kein Testgerät im Zugriff** — Gernots
Anlage hat keine Klimaanlage, die Dev-Boxen auch nicht. Alles hier ist gegen
**Fixtures** abgenommen, nicht gegen echte MELCloud-Daten. Das ist vertretbar,
weil das Feld optional ist: wer keinen Modus-Sensor zuordnet, merkt nichts. Es
ist aber keine Aussage darüber, wie sich die Hersteller-Vielfalt in freier
Wildbahn verhält.

**Der Sprengsatz, auf den es hier ankommt** (Konzept §9, Auftrag §Abnahme):
`test_s2_der_modus_landet_beim_richtigen_geraet` hebelt die **Zuordnung**
Entity→Investition aus, nicht die Summe. Ein Summen-Prüfer wäre an dieser
Stelle stumm — *bei falscher Zuordnung bleibt jede Summe gleich*, es steht nur
der Modus des einen Geräts beim anderen.

Konzept: `docs/KONZEPT-263-klima-split.md` §3.3 · §6.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.betriebsmodus import (
    AUS,
    BETRIEBSMODUS_KANON,
    ENTFEUCHTEN,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    UNBESTIMMT,
    normalisiere_betriebsmodus,
)


# ============================================================================
# S1 — Kanon und Normalisierung
# ============================================================================

@pytest.mark.parametrize(("roh", "erwartet"), [
    ("heat", HEIZEN),
    ("cool", KUEHLEN),
    ("dry", ENTFEUCHTEN),
    ("fan_only", LUEFTEN),
    ("off", AUS),
    # Die Automatik-Stellungen: das Gerät entscheidet selbst, und ohne
    # `hvac_action` weiß eedc nicht, was es tut. Einer Seite zugeschlagen wäre
    # eine erfundene Aufteilung (ADR-002/P4).
    ("auto", UNBESTIMMT),
    ("heat_cool", UNBESTIMMT),
    # Groß-/Kleinschreibung und Randleerzeichen sind egal; deutsche
    # Schreibweisen fangen selbstgebaute Template-Sensoren ab.
    ("HEAT", HEIZEN),
    ("  cool  ", KUEHLEN),
    ("Heizen", HEIZEN),
    ("kühlen", KUEHLEN),
])
def test_s1_hersteller_zustand_wird_zum_kanon(roh, erwartet):
    assert normalisiere_betriebsmodus(roh) == erwartet


@pytest.mark.parametrize("roh", ["unknown", "unavailable", "", None])
def test_s1_kein_zustand_ist_None_und_nicht_unbestimmt(roh):
    """Der Unterschied, den der Anwender später sehen können muss.

    `None` heißt „eedc hat nicht hingesehen" (Entity fehlt, HA-Ausfall);
    `unbestimmt` heißt „hingesehen, Seite nicht zuordenbar" (Automatik ohne
    Ist-Signal). Die zwei ineinander zu übersetzen wäre eine erfundene Aussage
    über die Datenlage — und genau das trennt später „Abdeckung niedrig" von
    „das Gerät lief in einer anderen Betriebsart".
    """
    assert normalisiere_betriebsmodus(roh) is None


def test_s1_unbekannter_aber_vorhandener_wert_ist_unbestimmt():
    """Die Gegenrichtung: gemeldet, aber nicht einzuordnen.

    Ein Hersteller-Wert, den eedc nicht kennt, ist **kein** Sensor-Ausfall.
    Ihn auf `None` abzubilden ließe die Abdeckungs-Kennzahl später aussehen,
    als hätte eedc nicht gemessen.
    """
    assert normalisiere_betriebsmodus("waermepumpe_spezialmodus") == UNBESTIMMT


def test_s1_hvac_action_schlaegt_den_eingestellten_modus():
    """`hvac_action` ist der Ist-Betrieb — wo sie da ist, gewinnt sie (D2)."""
    assert normalisiere_betriebsmodus("heat", "cooling") == KUEHLEN
    assert normalisiere_betriebsmodus("auto", "heating") == HEIZEN


def test_s1_unbekannte_hvac_action_verwirft_den_modus_nicht():
    """Sonst würde eine exotische Integration den vorhandenen Modus löschen."""
    assert normalisiere_betriebsmodus("heat", "irgendwas") == HEIZEN


def test_s1_idle_ist_nicht_aus():
    """Standby ist kein Aus — bei kingcap1 sind das 10 W Dauerverbrauch (D6).

    Das Außengerät versorgt drei Innengeräte samt WLAN. Diese Zeit einer
    Heiz- oder Kühlseite zuzuschlagen wäre falsch, sie „aus" zu nennen
    ebenfalls.
    """
    assert normalisiere_betriebsmodus("heat", "idle") == UNBESTIMMT


def test_s1_jeder_kanonwert_ist_erreichbar():
    """Negativprobe gegen eine Tabelle, die einen Kanonwert nie ausgibt."""
    erreicht = {
        normalisiere_betriebsmodus(s)
        for s in ("heat", "cool", "dry", "fan_only", "off", "auto")
    }
    assert erreicht == set(BETRIEBSMODUS_KANON)


# ============================================================================
# S1 — der Zustands-Lesepfad steht NEBEN dem numerischen, nicht darin
# ============================================================================

def test_s1_der_numerische_lesepfad_ist_unveraendert():
    """D8-Auflage: `get_sensor_history` bleibt `float`-only.

    Der Bestandspfad hat viele Aufrufer, und keiner von ihnen will einen
    String. Der neue Weg steht daneben — deshalb prüft diese Probe, dass die
    Bestands-Funktion einen Zustand weiterhin **verwirft**, statt ihn
    durchzulassen.
    """
    from backend.services.ha_state_service import _state_wert_und_einheit

    assert _state_wert_und_einheit({"state": "heat"}) is None
    assert _state_wert_und_einheit({"state": "42", "attributes": {}}) == (42.0, "")


def test_s1_der_zustandspfad_behaelt_den_string():
    from backend.services.ha_state_service import _state_hvac_action, _state_zustand

    assert _state_zustand({"state": "heat"}) == "heat"
    assert _state_zustand({"state": "unavailable"}) is None
    assert _state_zustand(None) is None
    assert _state_hvac_action({"state": "heat", "attributes": {"hvac_action": "heating"}}) == "heating"
    assert _state_hvac_action({"state": "heat", "attributes": {}}) is None


def test_s1_zustandsfelder_sind_im_sot_markiert_und_nicht_verstreut():
    """Die Weiche steht am Feld, nicht als `if key ==` an drei Stellen."""
    from backend.core.field_definitions import (
        ZUSTAND_LIVE_FELDER,
        get_feld_bedarf,
        ist_zustand_feld,
    )

    assert ("waermepumpe", "betriebsmodus") in ZUSTAND_LIVE_FELDER
    assert ist_zustand_feld("betriebsmodus") is True
    assert ist_zustand_feld("betriebsmodus", "waermepumpe") is True
    # Die Umkehrung gehört dazu: ein Messwert darf hier nicht landen.
    assert ist_zustand_feld("soc") is False
    assert ist_zustand_feld("leistung_w") is False
    # E-E: optional, und für JEDE Wärmepumpenart.
    assert get_feld_bedarf("waermepumpe", "betriebsmodus") == ("optional", None)


@pytest.mark.parametrize("wp_art", ["luft_luft", "luft_wasser", "sole_wasser", "grundwasser"])
def test_s1_das_feld_bekommt_jede_waermepumpenart(wp_art):
    """Konzept §7 E-E, und die Begründung ist gemessen, nicht vorsorglich.

    azywietz-webs zwei Klimaanlagen laufen als `luft_wasser`, weil das Feld
    „Wärmepumpenart" als Community-Einstellung beschriftet war. Wer nur
    `luft_luft` bedient, baut an genau der Gruppe vorbei, die das Thema meldet
    — und es gibt Luft-Wasser-Wärmepumpen **mit** Kühlfunktion.
    """
    from backend.core.field_definitions import get_live_felder_fuer_investition

    keys = [f["key"] for f in get_live_felder_fuer_investition("waermepumpe", {"wp_art": wp_art})]
    assert "betriebsmodus" in keys


def test_s1_der_live_poller_zieht_den_modus_nicht_mit():
    """Sonst liefe alle 5 Sekunden ein Abruf, der garantiert `None` ergibt.

    `live_power_service` schickt jede Live-Zuordnung durch
    `normalize_to_w(float(state))`. Ein `climate`-Zustand ist dort kein Wert,
    sondern eine Ausnahme — und der Modus wird ohnehin einmal je
    Aggregationslauf gelesen, nicht im Sekundentakt.
    """
    from backend.models.anlage import Anlage
    from backend.services.live_sensor_config import extract_live_config

    anlage = Anlage(
        anlagenname="X",
        sensor_mapping={"investitionen": {"7": {"live": {
            "leistung_w": "sensor.wp_leistung",
            "betriebsmodus": "climate.wohnzimmer",
        }}}},
    )
    _, inv_live, _, _ = extract_live_config(anlage)
    assert inv_live["7"] == {"leistung_w": "sensor.wp_leistung"}


async def test_s1_der_picker_laesst_climate_zu_und_sonst_nichts():
    """Ohne diese Freigabe ist S1 wirkungslos — und das stand in keinem Befund.

    Der Modus liegt in HA als eigene **`climate`**-Entität vor (D1). Der
    Domain-Test im Entity-Picker verwarf sie bis 2026-08-18 **unbedingt**: er
    steht vor der `filter_energy`-Auswertung, also half auch das Abschalten des
    Energie-Filters nicht. Ein Anwender hätte den Sensor nicht auswählen
    können, egal wie gut der Lesepfad ist.
    """
    from backend.api.routes.datenquellen import _ha_sensor_relevant

    klima = {"entity_id": "climate.wohnzimmer", "state": "heat", "attributes": {}}
    text = {"entity_id": "sensor.klima_modus", "state": "heat", "attributes": {}}
    licht = {"entity_id": "light.flur", "state": "on", "attributes": {}}

    # Zustandsfeld: climate UND sensor, ohne Energie-Filter.
    assert _ha_sensor_relevant(klima, True, zustand=True) is True
    assert _ha_sensor_relevant(text, True, zustand=True) is True
    # Aber nicht die halbe Instanz — der Picker bleibt eine Auswahl.
    assert _ha_sensor_relevant(licht, True, zustand=True) is False
    # Gegenprobe: für ein normales Feld bleibt alles, wie es war.
    assert _ha_sensor_relevant(klima, False, zustand=False) is False


def test_s1_der_modus_bekommt_kein_mqtt_topic():
    """Der Inbound-Parser ist `float(payload)` — ein Modus käme nie an.

    Ein Topic anzubieten, auf das niemand publizieren kann, ist dieselbe
    Klasse wie ein Daten-Checker-Hinweis, den niemand auflösen kann (P-6).
    Deshalb bleibt `topic` leer und `nur_ha` greift auf der Fläche.
    """
    from backend.core.field_definitions import get_live_felder_fuer_investition

    modus = next(
        f for f in get_live_felder_fuer_investition("waermepumpe", {"wp_art": "luft_luft"})
        if f["key"] == "betriebsmodus"
    )
    assert modus.get("zustand") is True
    # Und der Hinweis sagt es dem Anwender, statt ihn suchen zu lassen.
    assert "MQTT" in modus["hinweis"]


# ============================================================================
# S2 — Mitschreiben: die Verweildauer entscheidet, nicht der letzte Wert
# ============================================================================

class _FakeHaService:
    """Liefert eine feste Zustands-Historie — es gibt kein Testgerät (s. Kopf).

    `rand_liefern` bildet die **zwei möglichen Verhaltensweisen** von HAs
    `/api/history/period` ab, und das ist kein Detail: HA gibt normalerweise
    als ersten Eintrag den Zustand **zu Beginn** des Fensters zurück, auch wenn
    die letzte Änderung lange davor lag. Ob das mit `minimal_response` und nach
    einer recorder-Purge immer so ist, kann hier niemand messen — es gibt kein
    Testgerät. Deshalb prüfen die Proben unten **beide** Fälle: mit Randeintrag
    (`True`) und ohne (`False`, dann trägt allein der Ein-Tag-Vorlauf im
    Produktcode). Ein Fake, der nur den bequemen Fall kennt, hätte den Vorlauf
    als unnötig erscheinen lassen.

    ⛔ **Und ein Fake, der eine Spalte gar nicht kennt, deckt sie auch nicht
    ab.** Bis 2026-08-20 lieferte dieser Fake **Paare** ``(ts, zustand)`` — die
    `hvac_action` kam darin schlicht nicht vor. Damit konnte keine Probe hier
    bemerken, dass der Produktivpfad sie verlor: er verlor etwas, das der Fake
    nie geliefert hatte. Seither sind es **Tripel** ``(ts, zustand, aktion)``,
    wie `get_zustand_history` sie zurückgibt. Fixtures dürfen weiterhin Paare
    schreiben (dann ist die Aktion ``None``) — wer die Aktion prüfen will,
    schreibt sie als drittes Element hin.
    """

    def __init__(self, historie: dict, *, rand_liefern: bool = True):
        self._historie = historie
        self._rand_liefern = rand_liefern
        self.is_available = True
        self.gefragt: list[str] = []

    @staticmethod
    def _tripel(punkt):
        """Fixture-Punkt → ``(ts, zustand, aktion)``; Paare bekommen ``None``."""
        return punkt if len(punkt) == 3 else (punkt[0], punkt[1], None)

    async def get_zustand_history(self, entity_ids, start, end):
        self.gefragt = list(entity_ids)
        ergebnis = {}
        for eid in entity_ids:
            punkte = [self._tripel(p) for p in self._historie.get(eid, [])]
            im_fenster = [(ts, w, a) for ts, w, a in punkte if start <= ts < end]
            if self._rand_liefern:
                davor = [(ts, w, a) for ts, w, a in punkte if ts < start]
                if davor:
                    im_fenster = [(start, davor[-1][1], davor[-1][2]), *im_fenster]
            ergebnis[eid] = im_fenster
        return ergebnis


async def _modus_je_stunde(
    db, monkeypatch, *, historie, mapping,
    wp_bezeichnungen=("Klima",), rand_liefern: bool = True,
):
    """Legt Anlage + Wärmepumpen an und ruft den echten Aggregations-Helper."""
    from sqlalchemy import select

    from backend.models import Anlage, Investition
    from backend.services.energie_profil import _helpers

    anlage = Anlage(anlagenname="K2", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    ids = []
    for bez in wp_bezeichnungen:
        inv = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=bez,
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
            parameter={"wp_art": "luft_luft"},
        )
        db.add(inv)
        await db.flush()
        ids.append(inv.id)
    await db.commit()

    fake = _FakeHaService(historie, rand_liefern=rand_liefern)
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service", lambda: fake
    )

    geladen = (await db.execute(select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    ergebnis = await _helpers._get_betriebsmodus_history(
        geladen, mapping(ids), date(2025, 6, 15), db
    )
    return ergebnis, ids, fake


def _t(stunde: int, minute: int = 0) -> datetime:
    return datetime(2025, 6, 15, stunde, minute)


async def test_s2_die_laengste_verweildauer_gewinnt_die_stunde(db, monkeypatch):
    """Der Kern von S2 — und der Grund, warum eine SoC-Kopie falsch wäre.

    Ein SoC ist ein Messwert; über eine Stunde wird gemittelt. Ein Modus ist
    ein **Zustand**, und ein Zustand hat eine **Dauer**. Wer um 07:58 von
    Heizen auf Aus stellt, hat diese Stunde geheizt (58 von 60 Minuten) — der
    naheliegende „letzter Wert der Stunde" käme hier auf „aus" und wäre falsch.
    """
    historie = {"climate.k": [(_t(6, 0), "heat"), (_t(7, 58), "off")]}
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie=historie,
        mapping=lambda i: {"investitionen": {str(i[0]): {"live": {"betriebsmodus": "climate.k"}}}},
    )
    assert ergebnis[7][ids[0]] == HEIZEN     # 58 min heizen vs. 2 min aus
    assert ergebnis[8][ids[0]] == AUS        # danach durchgehend aus


@pytest.mark.parametrize("rand_liefern", [True, False], ids=["HA-Randeintrag", "nur-Vorlauf"])
async def test_s2_ein_modus_ohne_neuen_punkt_wird_fortgeschrieben(db, monkeypatch, rand_liefern):
    """HA schreibt nur bei Änderung — ohne Fortschreibung wäre fast alles leer.

    Eine Klimaanlage, die den ganzen Winter auf „Heizen" steht, liefert im
    Januar **einen** Punkt. Die übrigen 743 Stunden hätten sonst kein Signal,
    obwohl das Gerät durchgehend geheizt hat. Genau dieser Fall ist laut D11
    der Normalfall: der Modus wird saisonal gestellt, nicht täglich.

    Beide HA-Verhaltensweisen sind abgedeckt (s. `_FakeHaService`): mit
    Randeintrag am Fensteranfang **und** ohne — im zweiten Fall trägt allein
    der Ein-Tag-Vorlauf, den `_get_betriebsmodus_history` abruft. Die letzte
    Änderung liegt hier zwei Wochen zurück, also greift bei `rand_liefern=False`
    auch der Vorlauf nicht mehr: dann bleibt der Tag ehrlich leer, statt einen
    Modus zu erfinden.
    """
    historie = {"climate.k": [(datetime(2025, 6, 1, 9, 0), "cool")]}
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie=historie, rand_liefern=rand_liefern,
        mapping=lambda i: {"investitionen": {str(i[0]): {"live": {"betriebsmodus": "climate.k"}}}},
    )
    if rand_liefern:
        assert len(ergebnis) == 24
        assert all(je_geraet[ids[0]] == KUEHLEN for je_geraet in ergebnis.values())
    else:
        assert ergebnis == {}


async def test_s2_der_ein_tag_vorlauf_traegt_ueber_mitternacht(db, monkeypatch):
    """Warum `_get_betriebsmodus_history` einen Tag früher anfragt.

    Selbst wenn HA gar keinen Randeintrag lieferte, muss der Zustand von
    gestern Abend den heutigen Morgen tragen — sonst stünde jede Anlage jeden
    Tag bis zur ersten Änderung ohne Signal da, und bei saisonal gestelltem
    Modus (D11) wären das **alle** Tage.
    """
    historie = {"climate.k": [(datetime(2025, 6, 14, 21, 0), "heat")]}
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie=historie, rand_liefern=False,   # nur der Vorlauf kann helfen
        mapping=lambda i: {"investitionen": {str(i[0]): {"live": {"betriebsmodus": "climate.k"}}}},
    )
    assert len(ergebnis) == 24
    assert ergebnis[0][ids[0]] == HEIZEN


async def test_s2_ohne_signal_bleibt_die_stunde_leer_statt_unbestimmt(db, monkeypatch):
    """„Nicht hingesehen" ist kein Betriebsmodus.

    Ein leerer Tag darf nicht als 24 Stunden `unbestimmt` erscheinen — das
    sähe später aus wie „das Gerät lief in einer anderen Betriebsart", statt
    wie „es gab kein Signal". Die zwei Fälle trägt die Abdeckungs-Kennzahl.
    """
    ergebnis, _, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie={"climate.k": []},
        mapping=lambda i: {"investitionen": {str(i[0]): {"live": {"betriebsmodus": "climate.k"}}}},
    )
    assert ergebnis == {}


async def test_s2_ohne_zugeordneten_sensor_wird_HA_gar_nicht_gefragt(db, monkeypatch):
    """Das Feld ist optional — wer es nicht pflegt, zahlt keinen Abruf."""
    ergebnis, _, fake = await _modus_je_stunde(
        db, monkeypatch,
        historie={"climate.k": [(_t(6), "heat")]},
        mapping=lambda i: {"investitionen": {str(i[0]): {"live": {"leistung_w": "sensor.x"}}}},
    )
    assert ergebnis == {}
    assert fake.gefragt == []


async def test_s2_der_modus_landet_beim_richtigen_geraet(db, monkeypatch):
    """⚑ **Der Sprengsatz-Träger** (Auftrag §Abnahme, Konzept §9).

    Zwei Klimaanlagen, zwei Entities, zwei **verschiedene** Modi zur selben
    Stunde. Wer die Zuordnung Entity→Investition vertauscht, ändert **keine
    einzige Summe** — es steht nur der Modus des einen Geräts beim anderen,
    und später zählt der Kühlstrom des Wohnzimmers als Heizstrom des
    Schlafzimmers. Ein Summen-Prüfer wäre hier stumm; deshalb prüft diese
    Probe die Zuordnung selbst.
    """
    historie = {
        "climate.wohnen": [(_t(5), "heat")],
        "climate.schlafen": [(_t(5), "cool")],
    }
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie=historie,
        wp_bezeichnungen=("Wohnzimmer", "Schlafzimmer"),
        mapping=lambda i: {"investitionen": {
            str(i[0]): {"live": {"betriebsmodus": "climate.wohnen"}},
            str(i[1]): {"live": {"betriebsmodus": "climate.schlafen"}},
        }},
    )
    # Vor dem ersten Punkt gibt es kein Signal — auch das gehört geprüft,
    # sonst ließe sich die Zuordnung mit einer Fortschreibung „reparieren".
    assert all(stunde not in ergebnis for stunde in range(5))
    for stunde in range(5, 24):
        assert ergebnis[stunde][ids[0]] == HEIZEN, f"Stunde {stunde}: Wohnzimmer"
        assert ergebnis[stunde][ids[1]] == KUEHLEN, f"Stunde {stunde}: Schlafzimmer"


async def test_s2_zwei_geraete_duerfen_dieselbe_entity_teilen(db, monkeypatch):
    """D3: Der Modus gehört dem Außengerät, nicht dem Innengerät.

    Ein Innengerät auf „Heizen" bei kühlenden anderen tut in einer
    2-Rohr-Anlage nichts — **ein** Signal je Außengerät genügt, und dann steht
    derselbe Modus bei allen daran hängenden Investitionen.
    """
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie={"climate.aussen": [(_t(4), "cool")]},
        wp_bezeichnungen=("Innen 1", "Innen 2"),
        mapping=lambda i: {"investitionen": {
            str(i[0]): {"live": {"betriebsmodus": "climate.aussen"}},
            str(i[1]): {"live": {"betriebsmodus": "climate.aussen"}},
        }},
    )
    assert ergebnis[12] == {ids[0]: KUEHLEN, ids[1]: KUEHLEN}


async def test_s2_die_stundenzeile_traegt_den_modus(db, monkeypatch):
    """Die Spalte existiert, ist schreibbar und unterscheidet NULL von Inhalt."""
    from sqlalchemy import select

    from backend.models import Anlage
    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage = Anlage(anlagenname="Spalte", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=date(2025, 6, 15), stunde=10,
        betriebsmodus_je_wp={"7": HEIZEN},
    ))
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=date(2025, 6, 15), stunde=11,
        betriebsmodus_je_wp=None,
    ))
    await db.commit()

    zeilen = {z.stunde: z for z in (await db.execute(
        select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage.id)
    )).scalars().all()}
    assert zeilen[10].betriebsmodus_je_wp == {"7": HEIZEN}
    # `none_as_null=True`: echtes SQL-NULL, nicht die Zeichenkette "null" —
    # sonst fände eine spätere Altbestands-Erkennung je nach Herkunft die eine
    # Hälfte nicht (dieselbe Falle wie bei `soc_je_speicher`).
    assert zeilen[11].betriebsmodus_je_wp is None


# ============================================================================
# S1 — der Daten-Checker-Hinweis
# ============================================================================

async def _checker_meldungen(db, *, wp_art: str, mapping: dict | None = None, aktiv: bool = True):
    from sqlalchemy import select

    from backend.models import Anlage, Investition
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(
        anlagenname="Checker", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1), sensor_mapping=mapping or {},
    )
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wohnzimmer",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        parameter={"wp_art": wp_art}, aktiv=aktiv,
    )
    db.add(inv)
    await db.commit()

    if mapping is not None:
        anlage.sensor_mapping = {"investitionen": {
            str(inv.id): m for m in mapping.get("investitionen", {}).values()
        }} if mapping.get("investitionen") else mapping
        await db.commit()

    geladen = (await db.execute(select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    checker = DatenChecker(db)
    return await checker._check_klima_modus_sensor(geladen)


async def test_s1_checker_meldet_die_klimaanlage_ohne_modus_sensor(db):
    """INFO mit einem Weg — nicht WARNING und nicht ohne Ausweg.

    Das Feld ist optional: ohne es rechnet alles weiter, es fehlt nur die
    Aufteilung. Eine Warnung stünde in keinem Verhältnis, ein Hinweis ohne Weg
    wäre die P-6-Falle.
    """
    ergebnisse = await _checker_meldungen(db, wp_art="luft_luft", mapping={})
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.schwere == "info"
    assert "Wohnzimmer" in e.meldung
    assert e.link == "/einstellungen/datenquellen"
    assert e.investition_id is not None
    # Der Weg gehört in den Text, und die Erwartung auch: es gibt kein Backfill.
    assert "Betriebsmodus" in e.details
    assert "nicht rückwirkend" in e.details


async def test_s1_checker_schweigt_bei_jeder_anderen_waermepumpenart(db):
    """Messbarkeit hängt an der Bauart — dieselbe Trennlinie wie bei F-41.

    Ob ein Gerät überhaupt kühlen kann, ist Bauart. Eine Luft-Wasser-Wärmepumpe
    bekäme sonst einen Hinweis auf eine Aufteilung, die sie nicht hat. Das
    **Feld** bietet die Fläche ihr trotzdem an (E-E) — wer eine Kühlfunktion
    hat, findet es dort.
    """
    for art in ("luft_wasser", "sole_wasser", "grundwasser"):
        assert await _checker_meldungen(db, wp_art=art, mapping={}) == []


async def test_s1_checker_bestaetigt_die_zugeordnete_klimaanlage(db):
    """Ohne den OK-Zweig könnte niemand sehen, dass die Zuordnung sitzt."""
    ergebnisse = await _checker_meldungen(
        db, wp_art="luft_luft",
        mapping={"investitionen": {"platzhalter": {"live": {"betriebsmodus": "climate.k"}}}},
    )
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == "ok"


async def test_s1_checker_laesst_stillgelegte_geraete_in_ruhe(db):
    """Ein abgemeldetes Gerät braucht keine Sensor-Zuordnung mehr."""
    assert await _checker_meldungen(db, wp_art="luft_luft", mapping={}, aktiv=False) == []


# ============================================================================
# F — der Ist-Betrieb überlebt den Weg von HA bis in die Stundenzeile
#
# ⛔ **Warum diese zwei Proben existieren, obwohl `test_s1_hvac_action_*`
# schon grün war.** Jene prüft `normalisiere_betriebsmodus("heat", "cooling")`
# — eine Signatur, die **kein Produktivpfad benutzte**. Der Pfad faltete die
# Aktion vorher in den Zustand (`get_zustand_history`) und normalisierte dann
# einargumentig; `_AKTION_ZU_KANON` war damit unerreichbar, und `cooling`
# landete über den `_ZUSTAND_ZU_KANON`-Default in `unbestimmt`. **Jedes Gerät
# mit Ist-Signal verlor seine gesamte Aufteilung** — Panasonic, Daikin, die
# meisten Luft-Wasser-Wärmepumpen. Ein Gerät ohne `hvac_action` war korrekt:
# *das bessere Signal verschlechterte das Ergebnis.*
#
# Die Lehre steckt in der Aufteilung der zwei Proben: eine prüft die **Naht zu
# HA** (rohe Antwort → getrennte Felder), die andere den **ganzen Weg** bis in
# `betriebsmodus_je_wp`. Eine Probe auf die Funktion allein hätte beides wieder
# nicht gesehen.
# ============================================================================

async def test_f_die_ha_antwort_haelt_zustand_und_aktion_getrennt():
    """Naht zu HA: `hvac_action` darf den Zustand nicht ersetzen.

    Das ist die Stelle, an der der Fehler saß — die Aktion wurde **anstelle**
    des Zustands in den Punkt geschrieben. Danach war nicht mehr
    unterscheidbar, ob `cool` der eingestellte Modus oder ein Ist-Betrieb war,
    und die Aktions-Tabelle blieb unerreichbar.
    """
    import httpx

    from backend.services.ha_state_service import HAStateService

    antwort = [[
        {
            "entity_id": "climate.k",
            "state": "cool",
            "attributes": {"hvac_action": "cooling"},
            "last_changed": "2025-06-15T08:00:00",
        },
        {
            "state": "cool",
            "attributes": {"hvac_action": "idle"},
            "last_changed": "2025-06-15T09:00:00",
        },
    ]]

    # `is_available` ist eine Property über `token` — der Token macht sie wahr.
    service = HAStateService.__new__(HAStateService)
    service.api_url = "http://ha.invalid/api"
    service.token = "t"
    assert service.is_available

    class _Antwort:
        status_code = 200

        @staticmethod
        def json():
            return antwort

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_a, **_k):
            return _Antwort()

    import unittest.mock

    with unittest.mock.patch.object(httpx, "AsyncClient", _Client):
        punkte = (await service.get_zustand_history(
            ["climate.k"], datetime(2025, 6, 15, 0, 0),
        ))["climate.k"]

    # Drei Felder, nicht zwei — und der Zustand bleibt der Zustand.
    assert [(p[1], p[2]) for p in punkte] == [("cool", "cooling"), ("cool", "idle")]


async def test_f_der_ist_betrieb_erreicht_die_stundenzeile(db, monkeypatch):
    """Der ganze Weg: HA-Historie mit `hvac_action` → `betriebsmodus_je_wp`.

    Die Anlage steht durchgehend auf `cool`. Von 00:00 bis 10:00 kühlt sie
    tatsächlich (`cooling`), danach wartet sie (`idle`) — Standby, kein
    Kühlbetrieb.

    **Der Sprengsatz:** Vor dem Fix stand in JEDER Stunde `unbestimmt`, weil
    die Aktion den Zustand ersetzte und `cooling` unbekanntes Vokabular war.
    Ein Prüfer, der nur „nicht leer" verlangt hätte, wäre grün geblieben.
    """
    ergebnis, ids, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie={"climate.k": [
            (_t(0, 0), "cool", "cooling"),
            (_t(10, 0), "cool", "idle"),
        ]},
        mapping=lambda ids: {"investitionen": {
            str(ids[0]): {"live": {"betriebsmodus": "climate.k"}}
        }},
    )

    assert ergebnis[5][ids[0]] == KUEHLEN, "Ist-Betrieb `cooling` muss Kühlen ergeben"
    assert ergebnis[20][ids[0]] == UNBESTIMMT, "`idle` ist weder Kühlen noch Aus"

    # Und die Gegenprobe, die den Unterschied trägt: DIESELBE Historie ohne
    # Ist-Signal ist eine reine Kühlstunde — auch nach 10:00. Wer die Aktion
    # ignoriert, bekommt genau das und merkt nichts.
    ohne_aktion, ids2, _ = await _modus_je_stunde(
        db, monkeypatch,
        historie={"climate.k": [(_t(0, 0), "cool")]},
        mapping=lambda ids: {"investitionen": {
            str(ids[0]): {"live": {"betriebsmodus": "climate.k"}}
        }},
    )
    assert ohne_aktion[20][ids2[0]] == KUEHLEN
