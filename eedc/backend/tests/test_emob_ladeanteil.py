"""Der abgeleitete PV-Anteil der Heimladung (F-16) — bis E6 ohne Test (M9).

``services/emob_ladeanteil.py`` (271 Zeilen) ist die SoT für die **Anwendung**
der PV-Anteil-Ableitung auf Monatszeilen. Rund fünfzehn E-Mob-Tests existieren,
**keiner erreichte dieses Modul** (AST-Messung 2026-08-24: 0 Importe im
Testbaum).

Vier Zusagen des Moduls stehen hier als Probe:

* **Ein gepflegter Wert gewinnt — auch eine gepflegte 0** (F-15-Klasse).
* **Angereichert wird der ANTEIL, nicht die Kilowattstunde** — die Trias
  ``ladung_kwh == pv + netz`` bleibt in jeder Zeile geschlossen (#262).
* **Es werden Kopien geschrieben** — nie das an die Session gebundene JSON-Dict.
* **Der Torwächter gilt je Monat, nicht global.**
"""

import pytest

from backend.services.emob_ladeanteil import (
    hat_gepflegten_pv_anteil,
    reichere_ladezeilen_an,
    reichere_monatszeilen_an,
)


class TestTorwaechter:
    """`hat_gepflegten_pv_anteil` — Anwesenheit des Schlüssels, nicht Größe."""

    def test_leere_quellen_sind_ungepflegt(self):
        assert hat_gepflegten_pv_anteil([], []) is False

    def test_zeile_ohne_schluessel_ist_ungepflegt(self):
        assert hat_gepflegten_pv_anteil([{"ladung_kwh": 100.0}]) is False

    def test_gepflegter_wert_schliesst_das_tor(self):
        assert hat_gepflegten_pv_anteil([{"ladung_pv_kwh": 40.0}]) is True

    def test_eine_gepflegte_NULL_schliesst_das_tor_ebenfalls(self):
        """F-15-Klasse: „diesen Monat kam nichts aus der Sonne" ist eine Aussage."""
        assert hat_gepflegten_pv_anteil([{"ladung_pv_kwh": 0.0}]) is True

    def test_ausdrueckliches_none_zaehlt_NICHT_als_gepflegt(self):
        assert hat_gepflegten_pv_anteil([{"ladung_pv_kwh": None}]) is False

    def test_das_tor_laeuft_ueber_BEIDE_quellen(self):
        """Wallbox ungepflegt, Fahrzeug gepflegt ⇒ der Anwender hat erfasst."""
        assert hat_gepflegten_pv_anteil(
            [{"ladung_pv_kwh": 12.0}], [{"ladung_kwh": 30.0}]
        ) is True

    def test_leere_zeilen_werden_uebersprungen(self):
        assert hat_gepflegten_pv_anteil([None, {}, {"ladung_kwh": 5.0}]) is False


class TestAnreicherung:
    """`reichere_ladezeilen_an` — Anteil statt Kilowattstunde, auf Kopien."""

    def test_ohne_quote_bleibt_alles_unveraendert(self):
        zeile = {"ladung_kwh": 100.0}
        ea, wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[zeile], wallbox_daten=[], quote=None
        )
        assert ea == [zeile] and wb == []
        assert abgeleitet is False

    def test_gepflegter_anteil_schlaegt_die_ableitung(self):
        zeile = {"ladung_kwh": 100.0, "ladung_pv_kwh": 10.0}
        ea, _wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[zeile], wallbox_daten=[], quote=0.8
        )
        assert ea[0]["ladung_pv_kwh"] == 10.0
        assert abgeleitet is False

    def test_quote_wird_auf_die_ladung_der_zeile_angewandt(self):
        ea, _wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[{"ladung_kwh": 100.0}], wallbox_daten=[], quote=0.6
        )
        assert ea[0]["ladung_pv_kwh"] == pytest.approx(60.0)
        assert ea[0]["ladung_netz_kwh"] == pytest.approx(40.0)
        assert abgeleitet is True

    def test_die_trias_bleibt_in_jeder_zeile_geschlossen(self):
        """#262: PV-Anteil über 100 % entstand, als kWh übernommen wurden."""
        ea, wb, _ = reichere_ladezeilen_an(
            eauto_daten=[{"ladung_kwh": 30.0}, {"ladung_kwh": 70.0}],
            wallbox_daten=[{"ladung_kwh": 250.0}],
            quote=0.42,
        )
        for zeile in (*ea, *wb):
            assert zeile["ladung_pv_kwh"] + zeile["ladung_netz_kwh"] == pytest.approx(
                zeile["ladung_kwh"]
            )
            assert 0 <= zeile["ladung_pv_kwh"] <= zeile["ladung_kwh"]

    def test_summe_ueber_die_zeilen_gleich_summe_mal_quote(self):
        zeilen = [{"ladung_kwh": k} for k in (10.0, 25.0, 65.0)]
        ea, _wb, _ = reichere_ladezeilen_an(
            eauto_daten=zeilen, wallbox_daten=[], quote=0.3
        )
        assert sum(z["ladung_pv_kwh"] for z in ea) == pytest.approx(100.0 * 0.3)

    def test_das_original_dict_wird_NICHT_angefasst(self):
        """Sonst landet eine Schaetzung beim naechsten `flag_modified` in der DB."""
        original = {"ladung_kwh": 100.0}
        ea, _wb, _ = reichere_ladezeilen_an(
            eauto_daten=[original], wallbox_daten=[], quote=0.5
        )
        assert original == {"ladung_kwh": 100.0}
        assert ea[0] is not original

    def test_zeile_ohne_ladung_bleibt_unangetastet(self):
        ea, _wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[{"ladung_kwh": 0.0}], wallbox_daten=[], quote=0.5
        )
        assert "ladung_pv_kwh" not in ea[0]
        assert abgeleitet is False

    def test_abgeleitet_wird_nicht_aus_der_quote_erraten(self):
        """Provenance-Signal: Quote vorhanden, aber nichts zu teilen."""
        _ea, _wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[{}, {"ladung_kwh": 0.0}], wallbox_daten=[], quote=0.9
        )
        assert abgeleitet is False

    def test_quote_null_teilt_alles_dem_netz_zu(self):
        ea, _wb, abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[{"ladung_kwh": 80.0}], wallbox_daten=[], quote=0.0
        )
        assert ea[0]["ladung_pv_kwh"] == 0.0
        assert ea[0]["ladung_netz_kwh"] == pytest.approx(80.0)
        assert abgeleitet is True


class TestMonatszeilenOrchestrierung:
    """`reichere_monatszeilen_an` — Gruppierung, Reihenfolge, Vorprüfung.

    Die Quote kommt hier über einen gestellten Lader; die Tagesebene selbst
    prüft ``test_energie_profil_rollup_kette.py``.
    """

    @pytest.fixture
    def quoten(self, monkeypatch):
        """Stellt `lade_abgeleitete_ladeanteile` und zählt seine Aufrufe."""
        aufrufe: list[tuple] = []
        werte: dict = {}

        async def _lader(db, anlage_id, *, von=None, bis=None):
            aufrufe.append((anlage_id, von, bis))
            return dict(werte)

        monkeypatch.setattr(
            "backend.services.emob_ladeanteil.lade_abgeleitete_ladeanteile", _lader
        )
        return werte, aufrufe

    @pytest.mark.asyncio
    async def test_leere_eingabe_liefert_leere_liste_ohne_query(self, quoten):
        _werte, aufrufe = quoten
        assert await reichere_monatszeilen_an(None, 1, []) == []
        assert aufrufe == []

    @pytest.mark.asyncio
    async def test_ohne_heimladung_faellt_KEINE_query_an(self, quoten):
        """Eine Anlage ohne E-Mobilitaet zahlt nichts (Entscheid 2026-08-08)."""
        _werte, aufrufe = quoten
        zeilen = [((2026, 1), False, {"ladung_kwh": 0.0})]
        assert await reichere_monatszeilen_an(None, 1, zeilen) == [{"ladung_kwh": 0.0}]
        assert aufrufe == []

    @pytest.mark.asyncio
    async def test_bei_durchgehend_gepflegtem_anteil_KEINE_query(self, quoten):
        _werte, aufrufe = quoten
        zeilen = [((2026, 1), False, {"ladung_kwh": 50.0, "ladung_pv_kwh": 20.0})]
        await reichere_monatszeilen_an(None, 1, zeilen)
        assert aufrufe == []

    @pytest.mark.asyncio
    async def test_reihenfolge_bleibt_erhalten(self, quoten):
        werte, _aufrufe = quoten
        werte[(2026, 1)] = 0.5
        zeilen = [
            ((2026, 1), False, {"ladung_kwh": 10.0, "wer": "auto"}),
            ((2026, 1), True, {"ladung_kwh": 20.0, "wer": "wallbox"}),
            ((2026, 1), False, {"ladung_kwh": 30.0, "wer": "auto2"}),
        ]
        ergebnis = await reichere_monatszeilen_an(None, 1, zeilen)
        assert [z["wer"] for z in ergebnis] == ["auto", "wallbox", "auto2"]
        assert [z["ladung_pv_kwh"] for z in ergebnis] == [5.0, 10.0, 15.0]

    @pytest.mark.asyncio
    async def test_der_torwaechter_gilt_JE_MONAT(self, quoten):
        """Januar gepflegt, Februar nicht ⇒ nur der Februar wird abgeleitet."""
        werte, _aufrufe = quoten
        werte[(2026, 2)] = 0.25
        zeilen = [
            ((2026, 1), False, {"ladung_kwh": 100.0, "ladung_pv_kwh": 90.0}),
            ((2026, 2), False, {"ladung_kwh": 100.0}),
        ]
        januar, februar = await reichere_monatszeilen_an(None, 1, zeilen)
        assert januar["ladung_pv_kwh"] == 90.0
        assert februar["ladung_pv_kwh"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_monat_ohne_aussage_bleibt_unveraendert(self, quoten):
        werte, _aufrufe = quoten          # bewusst leer: keine Aussage
        zeilen = [((2026, 3), False, {"ladung_kwh": 100.0})]
        (zeile,) = await reichere_monatszeilen_an(None, 1, zeilen)
        assert "ladung_pv_kwh" not in zeile

    @pytest.mark.asyncio
    async def test_die_query_spannt_nur_die_offenen_monate(self, quoten):
        """`von`/`bis` folgen den ungepflegten Monaten, nicht der Eingabe."""
        werte, aufrufe = quoten
        werte.update({(2026, 5): 0.5})
        zeilen = [
            ((2026, 1), False, {"ladung_kwh": 10.0, "ladung_pv_kwh": 1.0}),
            ((2026, 5), False, {"ladung_kwh": 10.0}),
            ((2026, 9), False, {"ladung_kwh": 10.0, "ladung_pv_kwh": 1.0}),
        ]
        await reichere_monatszeilen_an(None, 42, zeilen)
        assert aufrufe == [(42, (2026, 5), (2026, 5))]
