"""Drei rechnende Module ohne Test — Preis-Ø, Verbrauchsprognose, Pipeline (M9).

Gemessen am 2026-08-24 per AST, je **0** Importe im Testbaum:

* ``services/strompreis_aggregator.py`` (109 Z.) — verbrauchsgewichteter
  Monats-Ø, samt Abdeckung und Konfidenz.
* ``services/verbrauch_prognose_service.py`` (134 Z.) — stündliches
  Verbrauchsprofil mit Recency-Gewichtung und Drei-Stufen-Kaskade.
* ``services/monatsabschluss_aggregator.py`` (156 Z.) — die Pipeline nach dem
  Monatsabschluss. ⚠ Ihre Zusage ist eine **Fehler**-Zusage: jeder Schritt
  darf scheitern, ohne die anderen zu entwerten, und das Vollbackfill-Flag
  wird **auch bei Fehler** gesetzt (sonst Endlos-Retry bei defekter HA-DB).
  Genau das steht hier als Probe — ein Pfad, den ein Glücksfall-Test nie nimmt.
"""

from datetime import date, timedelta

import pytest

from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.monatsabschluss_aggregator import (
    run_post_monatsabschluss_aggregation,
)
from backend.services.strompreis_aggregator import (
    StrompreisAggregat,
    berechne_monats_durchschnittspreis,
)
from backend.services.verbrauch_prognose_service import (
    HALBWERTSZEIT_TAGE,
    _gewicht,
    _ist_werktag,
    get_verbrauch_prognose,
)
from backend.tests.factories import anlage


async def stunde(db, anlage_id, tag: date, stunde_nr: int, **werte):
    db.add(TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=stunde_nr, **werte
    ))
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# strompreis_aggregator
# ─────────────────────────────────────────────────────────────────────────────

class TestAbdeckungUndKonfidenz:
    """Reine Eigenschaften des Aggregats — keine Datenbank nötig."""

    def test_abdeckung_ist_der_anteil_der_sollstunden(self):
        a = StrompreisAggregat(None, 0.0, abgedeckte_stunden=360, sollstunden=720)
        assert a.abdeckung == pytest.approx(0.5)

    def test_ohne_sollstunden_keine_division(self):
        a = StrompreisAggregat(None, 0.0, abgedeckte_stunden=0, sollstunden=0)
        assert a.abdeckung == 0

    @pytest.mark.parametrize(
        "abgedeckt,soll,erwartet",
        [
            (100, 100, 95),   # > 95 %
            (96, 100, 95),
            (95, 100, 80),    # genau 95 % ⇒ noch nicht die Spitzenstufe
            (71, 100, 80),
            (70, 100, 60),    # genau 70 % ⇒ noch nicht die mittlere Stufe
            (0, 100, 60),
        ],
    )
    def test_konfidenz_stufen_und_ihre_grenzen(self, abgedeckt, soll, erwartet):
        a = StrompreisAggregat(None, 0.0, abgedeckt, soll)
        assert a.konfidenz == erwartet


class TestMonatsDurchschnittspreis:

    @pytest.mark.asyncio
    async def test_ohne_preisdaten_keine_aussage(self, db):
        a = await anlage(db)
        assert await berechne_monats_durchschnittspreis(a.id, 2026, 6, db) is None

    @pytest.mark.asyncio
    async def test_gewichtet_folgt_dem_verbrauch_nicht_der_stundenzahl(self, db):
        """Der teure Preis liegt in der Stunde mit viel Bezug ⇒ Ø zieht hoch."""
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 6, 1), 1, strompreis_cent=10.0,
                     netzbezug_kw=1.0)
        await stunde(db, a.id, date(2026, 6, 1), 2, strompreis_cent=30.0,
                     netzbezug_kw=9.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 6, db)
        assert ergebnis.gewichtet_cent == pytest.approx(28.0)   # (10+270)/10
        assert ergebnis.arithmetisch_cent == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_negativer_netzbezug_wird_auf_null_geklemmt(self, db):
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 6, 1), 1, strompreis_cent=10.0,
                     netzbezug_kw=-5.0)
        await stunde(db, a.id, date(2026, 6, 1), 2, strompreis_cent=30.0,
                     netzbezug_kw=2.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 6, db)
        assert ergebnis.gewichtet_cent == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_ohne_bezug_gibt_es_keinen_gewichteten_wert(self, db):
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 6, 1), 1, strompreis_cent=10.0,
                     netzbezug_kw=0.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 6, db)
        assert ergebnis.gewichtet_cent is None
        assert ergebnis.arithmetisch_cent == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_sollstunden_folgen_der_monatslaenge(self, db):
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 2, 1), 1, strompreis_cent=10.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 2, db)
        assert ergebnis.sollstunden == 28 * 24
        assert ergebnis.abgedeckte_stunden == 1

    @pytest.mark.asyncio
    async def test_stunden_ohne_preis_zaehlen_nicht_zur_abdeckung(self, db):
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 6, 1), 1, strompreis_cent=20.0,
                     netzbezug_kw=1.0)
        await stunde(db, a.id, date(2026, 6, 1), 2, netzbezug_kw=1.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 6, db)
        assert ergebnis.abgedeckte_stunden == 1

    @pytest.mark.asyncio
    async def test_fremder_monat_faellt_heraus(self, db):
        a = await anlage(db)
        await stunde(db, a.id, date(2026, 5, 31), 1, strompreis_cent=99.0,
                     netzbezug_kw=1.0)
        await stunde(db, a.id, date(2026, 6, 1), 1, strompreis_cent=20.0,
                     netzbezug_kw=1.0)
        ergebnis = await berechne_monats_durchschnittspreis(a.id, 2026, 6, db)
        assert ergebnis.arithmetisch_cent == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
# verbrauch_prognose_service
# ─────────────────────────────────────────────────────────────────────────────

class TestGewichtung:
    """Recency: Halbwertszeit 14 Tage."""

    def test_heute_wiegt_ganz(self):
        assert _gewicht(0) == 1.0

    def test_nach_einer_halbwertszeit_die_haelfte(self):
        assert HALBWERTSZEIT_TAGE == 14.0
        assert _gewicht(14) == pytest.approx(0.5)

    def test_nach_zwei_halbwertszeiten_ein_viertel(self):
        assert _gewicht(28) == pytest.approx(0.25)

    def test_das_gewicht_faellt_streng_monoton(self):
        werte = [_gewicht(t) for t in (0, 7, 14, 30, 60)]
        assert all(a > b for a, b in zip(werte, werte[1:]))

    @pytest.mark.parametrize(
        "tag,werktag",
        [
            (date(2026, 6, 1), True),    # Montag
            (date(2026, 6, 5), True),    # Freitag
            (date(2026, 6, 6), False),   # Samstag
            (date(2026, 6, 7), False),   # Sonntag
        ],
    )
    def test_werktag_endet_am_freitag(self, tag, werktag):
        assert _ist_werktag(tag) is werktag


class TestVerbrauchsprognose:

    async def _voller_tag(self, db, anlage_id, tag: date, kw: float):
        """24 Stunden — der Qualitätsfilter verlangt mindestens 20."""
        for h in range(24):
            await stunde(db, anlage_id, tag, h, verbrauch_kw=kw)

    @pytest.mark.asyncio
    async def test_ohne_daten_keine_prognose(self, db):
        a = await anlage(db)
        assert await get_verbrauch_prognose(a.id, date(2026, 6, 15), db) is None

    @pytest.mark.asyncio
    async def test_zu_wenige_vollstaendige_tage_geben_auf(self, db):
        a = await anlage(db)
        for h in range(10):                      # nur 10 Stunden ⇒ unvollständig
            await stunde(db, a.id, date(2026, 6, 8), h, verbrauch_kw=1.0)
        assert await get_verbrauch_prognose(a.id, date(2026, 6, 15), db) is None

    @pytest.mark.asyncio
    async def test_der_qualitaetsfilter_verlangt_20_stunden(self, db):
        """Pinnt die SCHWELLE, nicht nur „irgendwas fehlt".

        Ohne diesen Fall bleibt die Probe gruen, wenn der Filter von 20 auf 1
        faellt: der Fall darueber scheitert dann immer noch an der Tageszahl.
        Gemessen beim Bau dieser Datei — derselbe blinde Fleck wie bei der
        25-°C-Schwelle in `test_prognose_ertrag_tag.py`.
        """
        a = await anlage(db)
        ziel = date(2026, 6, 15)
        # Drei gleiche Wochentage (Montage), aber je nur 19 Stunden.
        for tage_zurueck in (7, 14, 21):
            tag = ziel - timedelta(days=tage_zurueck)
            for h in range(19):
                await stunde(db, a.id, tag, h, verbrauch_kw=1.0)
        assert await get_verbrauch_prognose(a.id, ziel, db) is None

        # Dieselben drei Tage mit der 20. Stunde ⇒ sie zaehlen.
        for tage_zurueck in (7, 14, 21):
            await stunde(
                db, a.id, ziel - timedelta(days=tage_zurueck), 19, verbrauch_kw=1.0
            )
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        assert ergebnis is not None
        assert ergebnis["daten_tage"] == 3

    @pytest.mark.asyncio
    async def test_drei_gleiche_wochentage_gewinnen_die_kaskade(self, db):
        a = await anlage(db)
        ziel = date(2026, 6, 15)                 # Montag
        for tage_zurueck in (7, 14, 21):
            await self._voller_tag(db, a.id, ziel - timedelta(days=tage_zurueck), 2.0)
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        assert ergebnis["basis"] == "gleicher_wochentag"
        assert ergebnis["daten_tage"] == 3
        assert ergebnis["stunden_kw"] == [2.0] * 24

    @pytest.mark.asyncio
    async def test_ohne_genug_montage_faellt_sie_auf_den_tagestyp(self, db):
        a = await anlage(db)
        ziel = date(2026, 6, 15)                 # Montag
        for tag in (9, 10, 11, 12, 8):           # Di–Fr + Mo ⇒ 5 Werktage
            await self._voller_tag(db, a.id, date(2026, 6, tag), 3.0)
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        assert ergebnis["basis"] == "tagestyp"
        assert ergebnis["daten_tage"] == 5

    @pytest.mark.asyncio
    async def test_zuletzt_zaehlen_alle_tage(self, db):
        a = await anlage(db)
        ziel = date(2026, 6, 15)                 # Montag
        # Drei Wochenendtage: weder genug Montage noch genug Werktage
        for tag in (6, 7, 13):
            await self._voller_tag(db, a.id, date(2026, 6, tag), 4.0)
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        assert ergebnis["basis"] == "alle"
        assert ergebnis["daten_tage"] == 3

    @pytest.mark.asyncio
    async def test_der_juengere_tag_zieht_das_profil_staerker(self, db):
        a = await anlage(db)
        ziel = date(2026, 6, 15)                 # Montag
        await self._voller_tag(db, a.id, date(2026, 6, 8), 10.0)    # 7 Tage alt
        await self._voller_tag(db, a.id, date(2026, 6, 1), 0.0)     # 14 Tage alt
        await self._voller_tag(db, a.id, date(2026, 5, 25), 0.0)    # 21 Tage alt
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        naiv = 10.0 / 3
        assert ergebnis["stunden_kw"][0] > naiv

    @pytest.mark.asyncio
    async def test_der_zieltag_selbst_zaehlt_nicht_mit(self, db):
        """Fenster endet GESTERN — sonst prognostiziert sie sich selbst."""
        a = await anlage(db)
        ziel = date(2026, 6, 15)
        for tage_zurueck in (7, 14, 21):
            await self._voller_tag(db, a.id, ziel - timedelta(days=tage_zurueck), 2.0)
        await self._voller_tag(db, a.id, ziel, 99.0)
        ergebnis = await get_verbrauch_prognose(a.id, ziel, db)
        assert ergebnis["zeitraum_bis"] == date(2026, 6, 14)
        assert max(ergebnis["stunden_kw"]) == pytest.approx(2.0)


# ─────────────────────────────────────────────────────────────────────────────
# monatsabschluss_aggregator — die Fehler-Zusagen der Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestMonatsabschlussPipeline:

    @pytest.fixture
    def schritte(self, monkeypatch):
        """Ersetzt die vier Pipeline-Schritte durch zählbare Attrappen."""
        protokoll: list[str] = []
        modul = "backend.services.monatsabschluss_aggregator"

        class _Backfill:
            status, geschrieben, verarbeitet = "ok", 3, 5
            von = bis = date(2026, 6, 1)
            missing_eids: list = []

        class _Split:
            geschrieben, widerspruch = 2, []

        async def _backfill_range(anlage, von, bis, db):
            protokoll.append(f"backfill:{von}..{bis}")
            return 4

        async def _rollup(anlage_id, jahr, monat, db):
            protokoll.append("rollup")
            return True

        async def _voll(anlage, db, *, bis):
            protokoll.append("vollbackfill")
            return _Backfill()

        async def _split(db, anlage_id, jahr, monat):
            protokoll.append("split")
            return _Split()

        monkeypatch.setattr(f"{modul}.backfill_range", _backfill_range)
        monkeypatch.setattr(f"{modul}.rollup_month", _rollup)
        monkeypatch.setattr(
            f"{modul}.resolve_and_backfill_from_statistics", _voll
        )
        monkeypatch.setattr(f"{modul}.schreibe_modus_split_monat", _split)
        return protokoll, monkeypatch, modul

    @pytest.mark.asyncio
    async def test_alle_vier_schritte_laufen_und_berichten(self, db, schritte):
        protokoll, _mp, _modul = schritte
        a = await anlage(db, vollbackfill_durchgefuehrt=False)
        ergebnis = await run_post_monatsabschluss_aggregation(a, 2026, 6, db)
        assert protokoll == [
            "backfill:2026-06-01..2026-06-30", "rollup", "vollbackfill", "split",
        ]
        assert ergebnis.backfill_count == 4
        assert ergebnis.rollup_ok is True
        assert ergebnis.vollbackfill_status == "ok"
        assert ergebnis.modus_split_geschrieben == 2

    @pytest.mark.asyncio
    async def test_das_dezember_fenster_endet_am_31(self, db, schritte):
        protokoll, _mp, _modul = schritte
        a = await anlage(db, vollbackfill_durchgefuehrt=True)
        await run_post_monatsabschluss_aggregation(a, 2026, 12, db)
        assert protokoll[0] == "backfill:2026-12-01..2026-12-31"

    @pytest.mark.asyncio
    async def test_vollbackfill_laeuft_nur_beim_ersten_mal(self, db, schritte):
        protokoll, _mp, _modul = schritte
        a = await anlage(db, vollbackfill_durchgefuehrt=True)
        await run_post_monatsabschluss_aggregation(a, 2026, 6, db)
        assert "vollbackfill" not in protokoll

    @pytest.mark.asyncio
    async def test_das_flag_wird_AUCH_BEI_FEHLER_gesetzt(self, db, schritte):
        """Sonst Endlos-Retry bei defekter HA-Datenbank — die Kernzusage."""
        protokoll, mp, modul = schritte

        async def _kaputt(anlage, db, *, bis):
            protokoll.append("vollbackfill-crash")
            raise RuntimeError("HA-DB unerreichbar")

        mp.setattr(f"{modul}.resolve_and_backfill_from_statistics", _kaputt)
        a = await anlage(db, vollbackfill_durchgefuehrt=False)
        await db.commit()

        await run_post_monatsabschluss_aggregation(a, 2026, 6, db)

        await db.refresh(a)
        assert a.vollbackfill_durchgefuehrt is True
        assert "vollbackfill-crash" in protokoll

    @pytest.mark.asyncio
    async def test_ein_gescheiterter_rollup_entwertet_die_pipeline_nicht(
        self, db, schritte
    ):
        protokoll, mp, modul = schritte

        async def _kaputt(anlage_id, jahr, monat, db):
            raise RuntimeError("Rollup kaputt")

        mp.setattr(f"{modul}.rollup_month", _kaputt)
        a = await anlage(db, vollbackfill_durchgefuehrt=False)
        ergebnis = await run_post_monatsabschluss_aggregation(a, 2026, 6, db)
        assert ergebnis.rollup_ok is False
        assert ergebnis.vollbackfill_status == "ok"      # Schritt 3 lief trotzdem
        assert ergebnis.modus_split_geschrieben == 2     # Schritt 4 ebenfalls

    @pytest.mark.asyncio
    async def test_ein_gescheiterter_modus_split_entwertet_nichts(
        self, db, schritte
    ):
        """Eine Anlage ohne Modus-Sensor ist der Normalfall."""
        protokoll, mp, modul = schritte

        async def _kaputt(db, anlage_id, jahr, monat):
            raise RuntimeError("kein Modus-Sensor")

        mp.setattr(f"{modul}.schreibe_modus_split_monat", _kaputt)
        a = await anlage(db, vollbackfill_durchgefuehrt=True)
        ergebnis = await run_post_monatsabschluss_aggregation(a, 2026, 6, db)
        assert ergebnis.rollup_ok is True
        assert ergebnis.modus_split_geschrieben == 0
