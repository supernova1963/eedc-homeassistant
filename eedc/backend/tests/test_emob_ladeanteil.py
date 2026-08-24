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

from backend.services.eauto_wirtschaftlichkeit import get_emob_heimladung_canonical
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

    def test_das_tor_fragt_NUR_die_kanonische_quelle(self):
        """Wallbox traegt die Ladung ⇒ allein IHR PV-Wert entscheidet.

        ⛔ **Diese Probe stand bis 2026-08-24 auf dem Kopf** — sie hiess
        ``test_das_tor_laeuft_ueber_BEIDE_quellen`` und behauptete ``True``.
        Sie hielt damit fest, was ``get_emob_heimladung_canonical`` gerade
        verwirft: Bei vorhandener Wallbox ist der E-Auto-Wert unbeachtlich, er
        darf also auch kein Veto gegen die Ableitung einlegen. Die Probe war
        eine Beschreibung des Bestands, keine abgenommene Entscheidung —
        Gernots Entscheid vom 24.08. hat sie ersetzt.
        """
        assert hat_gepflegten_pv_anteil(
            [{"ladung_pv_kwh": 12.0}], [{"ladung_kwh": 30.0}]
        ) is False

    def test_ohne_wallbox_entscheidet_das_fahrzeug(self):
        """Kein Wallbox-Total ⇒ das E-Auto IST die Quelle (Schuko/Steckerlader)."""
        assert hat_gepflegten_pv_anteil(
            [{"ladung_pv_kwh": 12.0}], [{}]
        ) is True

    def test_wallbox_ohne_ladung_macht_sie_nicht_zur_quelle(self):
        """Eine Wallbox-Zeile ohne Heimladung waehlt nicht die leere Quelle.

        Sonst waere das Tor offen, obwohl der Anwender am einzigen fuehrenden
        Geraet gepflegt hat — die Quellenwahl haengt an der **Ladung**, nicht an
        der Existenz einer Investition.
        """
        assert hat_gepflegten_pv_anteil(
            [{"ladung_pv_kwh": 0.0}], [{"ladevorgaenge": 3}]
        ) is True

    def test_wallbox_ist_quelle_und_selbst_gepflegt(self):
        assert hat_gepflegten_pv_anteil(
            [{}], [{"ladung_kwh": 30.0, "ladung_pv_kwh": 5.0}]
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
    async def test_ein_altwert_am_fahrzeug_verhindert_die_QUERY_nicht_mehr(
        self, quoten
    ):
        """Die Vorpruefung entscheidet, ob die Tagesebene ueberhaupt geladen wird.

        ⚑ **Ohne diese Probe waere die Korrektur wirkungslos geblieben.** Der
        Torwaechter sitzt an zwei Stellen: hier als Spar-Vorpruefung **vor** der
        Query und noch einmal in ``reichere_ladezeilen_an``. Haette nur die
        zweite die Quellenregel gelernt, waere die erste weiter
        kurzgeschlossen — die Quote waere nie geladen worden und keine Sicht
        haette sich geaendert. Genau die Klasse des ``hvac_action``-Waechters
        vom 20.08. (Layer gruen, Route unberuehrt).
        """
        werte, aufrufe = quoten
        werte[(2026, 1)] = 0.62
        zeilen = [
            ((2026, 1), False, {"ladung_pv_kwh": 130.0, "ladung_netz_kwh": 50.0}),
            ((2026, 1), True, {"ladung_kwh": 200.0}),
        ]
        ergebnis = await reichere_monatszeilen_an(None, 1, zeilen)
        assert aufrufe == [(1, (2026, 1), (2026, 1))]
        # Die Wallbox-Zeile — die Quelle — traegt jetzt die Aufteilung ...
        assert ergebnis[1]["ladung_pv_kwh"] == pytest.approx(124.0)
        assert ergebnis[1]["ladung_netz_kwh"] == pytest.approx(76.0)
        # ... und der Altwert am Fahrzeug steht unveraendert daneben.
        assert ergebnis[0]["ladung_pv_kwh"] == pytest.approx(130.0)

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

class TestQuelleUndTorwaechterWidersprechenSichNicht:
    """Ende zu Ende: was der Anwender sieht, nicht was eine Funktion liefert.

    ⚑ **Warum auf dem Pool und nicht auf dem Torwaechter.** Eine Probe allein
    auf ``hat_gepflegten_pv_anteil`` waere gruen gewesen, ohne dass sich fuer
    irgendeine Sicht etwas aendert — genau der Fehler des ``hvac_action``-
    Waechters vom 20.08. Deshalb laeuft jede Probe hier ueber
    ``get_emob_heimladung_canonical``, also ueber die Zahl, die in Cockpit,
    Komponenten-Hub und HA-Export landet.

    Der Bestand, den diese Klasse beschreibt, entsteht **nicht neu**: das
    Formular blendet die E-Auto-Aufteilung bei vorhandener Wallbox aus
    (``bedingung_anlage: keine_wallbox``). Es sind die Monate, die
    ``migrate_emob_canonical_source`` (v3.36.0) als *unaufloesbar* stehen liess
    — Gewinner ohne PV-Split, Verlierer mit PV.
    """

    #: Wallbox fuehrt 200 kWh Heimladung, aber ohne eigene Aufteilung.
    WALLBOX = [{"ladung_kwh": 200.0}]
    #: Am Fahrzeug steht noch die alte, laengst ignorierte Aufteilung.
    EAUTO_ALTWERT = [{"ladung_pv_kwh": 130.0, "ladung_netz_kwh": 50.0}]

    def _pool(self, eauto, wallbox, quote):
        ea, wb, _abgeleitet = reichere_ladezeilen_an(
            eauto_daten=eauto, wallbox_daten=wallbox, quote=quote
        )
        return get_emob_heimladung_canonical(
            eauto_imd_data=ea, wallbox_imd_data=wb
        ), ea

    def test_der_altwert_am_fahrzeug_unterdrueckt_die_ableitung_NICHT_mehr(self):
        """Der gemessene Schaden: 0 % PV, obwohl die Tagesebene 62 % kennt.

        Vor dem 24.08. lieferte genau dieser Bestand ``PV=0 / Netz=200`` — keine
        falsche Zahl, sondern **gar keine Aussage** ueber die Sonne.
        """
        pool, _ea = self._pool(self.EAUTO_ALTWERT, self.WALLBOX, 0.62)
        assert pool.quelle == "wallbox"
        assert pool.ladung_kwh == pytest.approx(200.0)
        assert pool.pv_kwh == pytest.approx(124.0)
        assert pool.netz_kwh == pytest.approx(76.0)

    def test_der_altwert_am_fahrzeug_bleibt_unangetastet(self):
        """Kein Bestand wird ueberschrieben — auch nicht in der Kopie.

        Die Zeile zaehlt nur nicht mehr gegen eine Quelle, die sie nicht ist.
        """
        _pool, ea = self._pool(self.EAUTO_ALTWERT, self.WALLBOX, 0.62)
        assert ea[0]["ladung_pv_kwh"] == pytest.approx(130.0)
        assert ea[0]["ladung_netz_kwh"] == pytest.approx(50.0)
        assert self.EAUTO_ALTWERT[0]["ladung_pv_kwh"] == pytest.approx(130.0)

    def test_ein_gepflegter_wallbox_wert_gewinnt_weiterhin(self):
        """Die Quelle selbst gepflegt ⇒ nichts wird abgeleitet (F-15-Klasse)."""
        pool, _ea = self._pool(
            [{}], [{"ladung_kwh": 200.0, "ladung_pv_kwh": 90.0}], 0.62
        )
        assert pool.pv_kwh == pytest.approx(90.0)
        assert pool.netz_kwh == pytest.approx(110.0)

    def test_ohne_wallbox_bleibt_das_fahrzeug_die_quelle(self):
        """Steckerlader: die gepflegte Aufteilung am E-Auto gilt unveraendert."""
        pool, _ea = self._pool(self.EAUTO_ALTWERT, [{}], 0.62)
        assert pool.quelle == "e-auto"
        assert pool.pv_kwh == pytest.approx(130.0)
        assert pool.netz_kwh == pytest.approx(50.0)

    def test_ohne_tagesebene_aendert_sich_nichts(self):
        """``quote=None`` heisst „keine Aussage" — dann bleibt es bei 0 kWh PV.

        Die Gegenprobe zur ersten Zusage: die Korrektur wirkt **nur**, wo die
        Tagesebene eine Quote liefert. Wer sie nicht hat, sieht dasselbe wie
        vorher — das gehoert zur ehrlichen Reichweite der Aenderung.
        """
        pool, _ea = self._pool(self.EAUTO_ALTWERT, self.WALLBOX, None)
        assert pool.pv_kwh == pytest.approx(0.0)
        assert pool.netz_kwh == pytest.approx(200.0)

    def test_die_trias_bleibt_in_jeder_zeile_geschlossen(self):
        """``ladung_kwh == pv + netz`` — die #262-Invariante, hier erneut."""
        pool, _ea = self._pool(self.EAUTO_ALTWERT, self.WALLBOX, 0.62)
        assert pool.pv_kwh + pool.netz_kwh == pytest.approx(pool.ladung_kwh)

