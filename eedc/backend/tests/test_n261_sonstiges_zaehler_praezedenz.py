"""N-261 · Teil B — der kWh-Zähler schlägt die Leistungs-Integration.

**Der Befund (Melder rapahl, 16.08.2026).** Sein Heizstab stand im Tagesverlauf
mit **5,59 kWh**, sein Energiemesser sagte **3,0 kWh**. Ursache: Ein Gerät unter
*Sonstiges* fiel in ``_resolve_counter_eid`` durch **alle** Zweige und landete im
Mean-Pfad — die Stunden-Energie kam also aus dem **Stundenmittel der Leistung**,
auch wenn ein kWh-Zähler gemappt war. Bei kurzen 6-kW-Impulsen ist so ein
Mittelwert grob; er hat es selbst vermutet („mächtige Impulse, die Riemann
durcheinander bringen könnten") und lag damit richtig.

⚠ **Zwei Dinge, die dieser Test NICHT prüft, damit die Grenze klar bleibt:**

* Das **Vorzeichen** — das kommt aus der Butterfly-Konvention (``seite``) und
  wird in der Anzeige abgestreift (`TagWerteTabelle::alsAnzeigewert`, Teil A).
  Der Zählerwert ist positiv, aber ``seite`` wirkt danach trotzdem.
* Die **Kurvenform** — die bleibt aus dem Leistungssensor
  (``kurven_leistung_mit_live_fallback``). Der Zähler ersetzt nur die Energie.
"""

import pytest

from backend.core.field_definitions import (
    SONSTIGES_VERBRAUCH_FELDER,
    sonstiges_feld_reihenfolge,
)
from backend.services.live_tagesverlauf_service import _resolve_counter_eid


def sensor(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


class TestSonstigesFeldReihenfolge:
    """Der Registry-SoT — eine Liste statt vier handgepflegter Kopien (N-259)."""

    def test_kanonischer_name_steht_vor_dem_legacy_zwilling(self):
        assert SONSTIGES_VERBRAUCH_FELDER == ("verbrauch_sonstig_kwh", "verbrauch_kwh")

    def test_verbraucher_liest_zuerst_den_verbrauch(self):
        assert sonstiges_feld_reihenfolge("verbraucher")[0] == "verbrauch_sonstig_kwh"

    def test_ohne_gepflegte_kategorie_gilt_verbraucher(self):
        # Dieselbe Lesart wie die Schreibpfade (`sonstiges_richtung`): Wer nichts
        # pflegt, wird als Verbraucher gelesen.
        assert sonstiges_feld_reihenfolge(None) == sonstiges_feld_reihenfolge("verbraucher")

    def test_erzeuger_liest_zuerst_die_erzeugung(self):
        assert sonstiges_feld_reihenfolge("erzeuger")[0] == "erzeugung_kwh"

    def test_jede_reihenfolge_enthaelt_alle_drei_felder_genau_einmal(self):
        # Either-Or-Gruppe: Kein Feld darf fehlen (sonst ist ein Gerät blind) und
        # keines doppelt stehen (sonst zählt es zweimal).
        for kategorie in (None, "verbraucher", "erzeuger"):
            felder = sonstiges_feld_reihenfolge(kategorie)
            assert sorted(felder) == sorted(
                {"erzeugung_kwh", "verbrauch_sonstig_kwh", "verbrauch_kwh"}
            ), kategorie


class TestZaehlerPraezedenzSonstiges:
    """Wo ein kWh-Zähler gemappt ist, gewinnt er gegen die Leistungs-Integration."""

    def test_verbraucher_mit_kanonischem_zaehler(self):
        felder = {"verbrauch_sonstig_kwh": sensor("sensor.heizstab_kwh")}
        eid = _resolve_counter_eid("sonstiges", None, felder, {"kategorie": "verbraucher"})
        assert eid == "sensor.heizstab_kwh"

    def test_ohne_gepflegte_kategorie_findet_er_ihn_trotzdem(self):
        # Rainers Lage: Kategorie gepflegt oder nicht — der Zähler muss greifen.
        felder = {"verbrauch_sonstig_kwh": sensor("sensor.heizstab_kwh")}
        assert _resolve_counter_eid("sonstiges", None, felder, None) == "sensor.heizstab_kwh"

    def test_legacy_zwilling_wird_noch_gelesen(self):
        # Altbestand im Mapping darf nicht in den Mean-Pfad zurückfallen.
        felder = {"verbrauch_kwh": sensor("sensor.alt")}
        assert _resolve_counter_eid("sonstiges", None, felder, None) == "sensor.alt"

    def test_erzeuger_nimmt_die_erzeugung(self):
        felder = {"erzeugung_kwh": sensor("sensor.bhkw_kwh")}
        eid = _resolve_counter_eid("sonstiges", None, felder, {"kategorie": "erzeuger"})
        assert eid == "sensor.bhkw_kwh"

    def test_nur_leistungssensor_bleibt_im_mean_pfad(self):
        # Kein erfundener Zähler: Wer nur Leistung gemappt hat, muss weiterhin
        # über das Stundenmittel laufen — sonst entstünde eine Energie aus nichts.
        felder = {"leistung_w": sensor("sensor.heizstab_w")}
        assert _resolve_counter_eid("sonstiges", None, felder, None) is None

    def test_ohne_jedes_mapping_kein_zaehler(self):
        assert _resolve_counter_eid("sonstiges", None, {}, None) is None


class TestUnveraenderteZweige:
    """Die bestehenden Typen dürfen sich durch die Erweiterung nicht bewegen."""

    def test_speicher_bleibt_bidirektional_im_mean_pfad(self):
        # Bewusst kein Zähler-Pfad: Das Vorzeichen (Laden/Entladen) IST hier die
        # Aussage und ginge über eine vorzeichenlose Zähler-Summe verloren.
        felder = {"verbrauch_sonstig_kwh": sensor("sensor.irgendwas")}
        assert _resolve_counter_eid("speicher", None, felder, None) is None

    @pytest.mark.parametrize(
        "typ,feld,eid",
        [
            ("waermepumpe", "stromverbrauch_kwh", "sensor.wp_kwh"),
            ("wallbox", "ladung_kwh", "sensor.wb_kwh"),
        ],
    )
    def test_wp_und_wallbox_unveraendert(self, typ, feld, eid):
        assert _resolve_counter_eid(typ, None, {feld: sensor(eid)}, None) == eid

    def test_wp_split_serie_hat_keinen_eigenen_zaehler(self):
        # Heizen/Warmwasser einzeln misst kein Zähler → Mean-Pfad, unverändert.
        felder = {"stromverbrauch_kwh": sensor("sensor.wp_kwh")}
        assert _resolve_counter_eid("waermepumpe", "heizen", felder, None) is None
