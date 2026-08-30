"""Drei Meldungen der Datenquellen-Fläche sagen die Wahrheit über sich selbst.

Schwesterdateien: test_datenquellen_validierung.py, test_daten_checker_stammdaten.py.

Anlass: rapahl, PN 91806 („Daten/Datenchecker", 2026-08-30), mit Bildern. Alle
drei Befunde sind Fund-am-Text bzw. -an-der-Bedingung — kein Rechenweg war
falsch, aber jede Meldung behauptete etwas, das so nicht zutraf.
"""
from backend.services.datenquellen_validierung import (
    finde_redundante_aggregate, finde_doppelmappings, _GRUPPEN_TEXT,
)


def _feld(fid, feld, typ="basis", belegt=True, hat_wert=True):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt, "hat_wert": hat_wert}


class TestVerdraengenBrauchtEinenWert:
    """Rainers Fall: ein gestempeltes Feld ohne Nachricht verdrängt nichts."""

    def _rainer(self, hat_wert):
        # Seine Lage: Netz kombiniert (±) liefert −1250 W; Einspeisung (W) und
        # Netzbezug (W) tragen MQTT-Standard-Topics aus der B8-Materialisierung,
        # auf denen nie etwas ankam.
        return [
            _feld("basis:netz_kombi_w", "netz_kombi_w"),
            _feld("basis:einspeisung_w", "einspeisung_w", hat_wert=hat_wert),
            _feld("basis:netzbezug_w", "netzbezug_w", hat_wert=hat_wert),
        ]

    def test_gestempeltes_feld_ohne_wert_meldet_nichts(self):
        out = finde_redundante_aggregate(self._rainer(hat_wert=False))
        assert "basis:netz_kombi_w" not in out, (
            "Der Kombi-Sensor liefert als einziger — er ist nicht wirkungslos"
        )

    def test_echt_belegtes_feld_verdraengt_weiterhin(self):
        """Die Gegenrichtung: der Hinweis bleibt, wo er stimmt.

        Ohne diese Zusicherung wäre der Fix eine stille Abschaltung — der
        Hinweis ist für #314 gebaut und dort richtig.
        """
        out = finde_redundante_aggregate(self._rainer(hat_wert=True))
        assert "basis:netz_kombi_w" in out
        assert out["basis:netz_kombi_w"]["grund"] == "netz_kombi"

    def test_ohne_hat_wert_gilt_die_alte_bedingung(self):
        """Ein Aufrufer ohne das neue Feld verliert nicht alle Hinweise."""
        alt = [{"id": f["id"], "feld": f["feld"], "typ": f["typ"], "belegt": True}
               for f in self._rainer(hat_wert=True)]
        assert "basis:netz_kombi_w" in finde_redundante_aggregate(alt)


class TestDoppelzaehlungNurBeiMengen:
    """Rainers Octopus-Sensor: derselbe Preis an zwei Feldern ist richtig."""

    EID = "sensor.octopus_heat_preis_cent"

    def test_preis_an_zwei_feldern_ist_keine_doppelzaehlung(self):
        out = finde_doppelmappings(
            {"basis:strompreis": self.EID, "inv:7:speicher_ladepreis_cent": self.EID},
            {"basis:strompreis": "ct/kWh", "inv:7:speicher_ladepreis_cent": "ct/kWh"},
        )
        assert out == {}, "Ein Preis wird nicht summiert — er gilt zweimal"

    def test_menge_an_zwei_feldern_bleibt_gemeldet(self):
        """#314 unverändert: bei kWh ist der Hinweis richtig und bleibt."""
        out = finde_doppelmappings(
            {"basis:netzbezug": "sensor.zaehler", "inv:3:ladung_kwh": "sensor.zaehler"},
            {"basis:netzbezug": "kWh", "inv:3:ladung_kwh": "kWh"},
        )
        assert set(out) == {"basis:netzbezug", "inv:3:ladung_kwh"}

    def test_mischfall_meldet_nur_die_mengen_haelfte(self):
        """Preis + zwei Mengen: die zwei Mengen zählen doppelt, der Preis nicht."""
        out = finde_doppelmappings(
            {"a": "sensor.x", "b": "sensor.x", "p": "sensor.x"},
            {"a": "kWh", "b": "kWh", "p": "ct/kWh"},
        )
        assert set(out) == {"a", "b"}
        assert "p" not in out["a"]["andere_felder"]

    def test_ohne_einheiten_gilt_das_alte_verhalten(self):
        out = finde_doppelmappings({"a": "sensor.x", "b": "sensor.x"})
        assert set(out) == {"a", "b"}


class TestHinweisTexteNennenDieHandlung:
    def test_gruppentexte_sagen_dass_nichts_zu_tun_ist(self):
        """Ein Zustandssatz neben einem Schalter wird als Aufforderung gelesen.

        Genau das ist passiert: „hier stand immer: bitte keine auswählen".
        """
        for schluessel, text in _GRUPPEN_TEXT.items():
            assert "nichts einzutragen" in text, f"{schluessel} nennt keine Handlung"
