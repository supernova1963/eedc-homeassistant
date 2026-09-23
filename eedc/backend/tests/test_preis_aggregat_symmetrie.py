"""Die gruppierte Preismessung sagt dasselbe wie die Einzelmonats-Messung.

Schwesterdateien: `test_aufgeloester_monatspreis_kaskade.py` (die vier Stufen
darüber), `test_zeittarif_ht_nt.py` (Stufe 3), `test_query_budget_monats_fakten.py`
(dass die Abfrage-Menge nicht zurückdriftet).

**Der Gegenstand.** Stufe 2 der Preis-Kaskade („gemessen") fragte die
Stundentabelle **je Monat und je Aufrufer** — an einer produktiven Anlage mit
39 Monaten waren das **117 Abfragen** für einen einzigen Aufruf von
`GET /monatsdaten/aggregiert`, jede davon über alle 16.391 Stundenzeilen, weil
`extract()` über der Datumsspalte den Index ausschaltet (gemessen 15.09.2026:
1,4 s von 2,4 s). An ihre Stelle tritt **eine** gruppierte Abfrage je Anfrage.

⛔ **Diese Datei ist die Bedingung dafür, dass das erlaubt ist.** Eine
Umstellung der Beschaffung darf keine Zahl bewegen; SQL und Python runden,
clampen und zählen aber nicht von selbst gleich. Drei Fallen sind hier
namentlich festgehalten:

1. **Negativer Netzbezug wird geclampt, nicht verworfen** — die Stunde zählt
   mit Gewicht 0 mit. **Gegenprobe gefahren** (15.09.2026): Nimmt man `MAX(…, 0)`
   aus der Abfrage, melden drei Proben dieser Datei rot.
2. **Die Monatsgrenzen** — 23 Uhr des Vormonats und 0 Uhr des Folgemonats
   dürfen nicht hineinrutschen (die Bereichsbedingung ersetzt `extract`).
3. **Eine Stunde ohne Bezug zählt mit** — in `abgedeckte_stunden` und im
   arithmetischen Ø, weil beide am Preis hängen, nicht am Bezug.

⛔ **Was hier ausdrücklich NICHT gilt**, obwohl es beim Bau so im Docstring
stand: Das `COALESCE` vor dem `MAX` rettet keine Zahl. `MAX(NULL, 0)` ist in
SQLite zwar `NULL`, aber `SUM` überspringt `NULL` und die Stunde trüge ohnehin 0
bei — ohne `COALESCE` bleiben alle fünf Proben grün (gemessen). Es steht im Code
als ausgesprochene Absicht, nicht als Schutz. *Eine Begründung, die niemand
rot machen kann, ist keine.*

⚠ **Die Erwartungswerte werden im Test von Hand nachgerechnet**, nicht von
einer der beiden Implementierungen abgeschrieben — sonst prüfte die Datei nur,
dass zwei Wege denselben Fehler machen.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage
from backend.tests.slot_saat import tep_zeilen
from backend.services.strompreis_aggregator import (
    berechne_monats_durchschnittspreis,
    lade_preis_aggregate_je_monat,
)


async def _anlage(db, name="Preismessung") -> int:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


def _stunde(d: date, stunde: int, preis, bezug, pv=None, einspeisung=None) -> dict:
    """Eine **Stunde** — Menge und Preis derselben Stunde, nicht derselben Zeile.

    ⭐ **N-387 (23.09.2026): `strompreis_cent` liegt forward.** Die Menge der
    Stunde `h` steht in Zeile `h` (backward), ihr Preis in Zeile `h-1` — über
    die Tagesgrenze in Zeile 23 des Vortags. `tep_zeilen` verteilt das; bis
    dahin legte diese Datei beides in dieselbe Zeile und schrieb damit den
    Versatz fest, den N-387 beschreibt. **Alle Erwartungswerte unten sind
    unverändert** — sie waren von Hand aus den Stunden gerechnet, nicht aus den
    Zeilen, und genau deshalb tragen sie die Umstellung.
    """
    return {"datum": d, "stunde": stunde, "strompreis_cent": preis,
            "netzbezug_kw": bezug, "pv_kw": pv, "einspeisung_kw": einspeisung}


async def _bestand(db) -> int:
    """Ein Bestand, der jede Falle genau einmal enthält.

    * **2025-03** — 3 Tage à 24 h zu 30 ct/1,0 kW, dazu vier Stunden mit
      **negativem** Bezug (−2,0) und zwei Stunden mit Bezug **NULL**.
    * **2025-04** — nur 10 Stunden (Teilabdeckung), 20 ct/2,0 kW.
    * **2025-05** — Preise vorhanden, Bezug **überall 0** (kein gewichteter Ø,
      aber ein arithmetischer).
    * **2025-06** — **keine** Preiszeilen (nur Bezug) ⇒ kein Eintrag.
    * **Randstunden** — 2025-02-28 23 Uhr und 2025-04-01 0 Uhr tragen Preise,
      die dem März **nicht** zufallen dürfen.
    """
    aid = await _anlage(db)
    stunden = [
        _stunde(date(2025, 3, tag), stunde, 30.0, 1.0)
        for tag in (1, 2, 3) for stunde in range(24)
    ]
    stunden += [_stunde(date(2025, 3, 10), stunde, 10.0, -2.0) for stunde in range(4)]
    stunden += [_stunde(date(2025, 3, 10), stunde, 50.0, None) for stunde in (5, 6)]
    stunden += [_stunde(date(2025, 4, 5), stunde, 20.0, 2.0) for stunde in range(10)]
    stunden += [_stunde(date(2025, 5, 7), stunde, 40.0, 0.0) for stunde in range(24)]
    stunden += [_stunde(date(2025, 6, 9), stunde, None, 3.0) for stunde in range(24)]
    stunden += [_stunde(date(2025, 2, 28), 23, 99.0, 9.0)]
    stunden += [_stunde(date(2025, 4, 1), 0, 88.0, 9.0)]
    # **2025-07** — A-2: vier Mittagsstunden mit vermiedenem Bezug (PV 3, Einspeisung 1
    # ⇒ EV 2) zu 10 ct, vier Abendstunden mit Bezug 2 kW zu 50 ct und ohne PV;
    # dazu eine Stunde, in der die Einspeisung die PV übersteigt (EV klemmt auf 0).
    stunden += [
        _stunde(date(2025, 7, 8), stunde, 10.0, 0.0, pv=3.0, einspeisung=1.0)
        for stunde in (11, 12, 13, 14)
    ]
    stunden += [
        _stunde(date(2025, 7, 8), stunde, 50.0, 2.0, pv=0.0, einspeisung=0.0)
        for stunde in (19, 20, 21, 22)
    ]
    stunden += [_stunde(date(2025, 7, 8), 23, 70.0, 0.0, pv=0.5, einspeisung=1.5)]
    db.add_all(tep_zeilen(aid, stunden))
    await db.flush()
    return aid


class TestBeideWegeSagenDasselbe:
    @pytest.mark.asyncio
    async def test_jeder_monat_stimmt_in_allen_vier_feldern_ueberein(self, db):
        aid = await _bestand(db)
        messung = await lade_preis_aggregate_je_monat(db, aid)

        for jahr, monat in ((2025, 3), (2025, 4), (2025, 5), (2025, 6), (2025, 7)):
            einzeln = await berechne_monats_durchschnittspreis(aid, jahr, monat, db)
            gruppiert = messung.hole(jahr, monat)
            if einzeln is None:
                assert gruppiert is None, f"{jahr}-{monat}: Einzelweg None, Gruppe nicht"
                continue
            assert gruppiert is not None, f"{jahr}-{monat}: Gruppe fehlt"
            assert gruppiert.gewichtet_cent == einzeln.gewichtet_cent
            assert gruppiert.arithmetisch_cent == einzeln.arithmetisch_cent
            assert gruppiert.abgedeckte_stunden == einzeln.abgedeckte_stunden
            assert gruppiert.sollstunden == einzeln.sollstunden
            # A-2 (18.09.2026): der EV-gewichtete Ø ist das fünfte Feld.
            assert gruppiert.ev_gewichtet_cent == einzeln.ev_gewichtet_cent

    @pytest.mark.asyncio
    async def test_erwartungswerte_von_hand_nachgerechnet(self, db):
        """Nicht abgeschrieben, sondern aus dem Seed gerechnet — sonst prüfte
        die Datei nur, dass beide Wege denselben Fehler machen."""
        aid = await _bestand(db)
        messung = await lade_preis_aggregate_je_monat(db, aid)

        # März: 72 h à 30 ct/1,0 kW + 4 h à 10 ct/−2,0 (⇒ 0) + 2 h à 50 ct/NULL (⇒ 0)
        #   gewichtet = 72·30·1 / 72·1 = 30,0
        #   arithmetisch = (72·30 + 4·10 + 2·50) / 78 = 2300/78 = 29,49
        #   abgedeckte Stunden = 78, Sollstunden = 31·24 = 744
        maerz = messung.hole(2025, 3)
        assert maerz.gewichtet_cent == 30.0
        assert maerz.arithmetisch_cent == round(2300 / 78, 2)
        assert maerz.abgedeckte_stunden == 78
        assert maerz.sollstunden == 744

        # April: 10 h à 20 ct/2,0 kW + die Randstunde 01.04. 0 Uhr (88 ct/9,0 kW)
        april = messung.hole(2025, 4)
        assert april.abgedeckte_stunden == 11
        assert april.gewichtet_cent == round((10 * 20 * 2 + 88 * 9) / (10 * 2 + 9), 2)

        # Mai: Preise, aber Bezug überall 0 ⇒ kein gewichteter Wert, arithmetisch 40
        mai = messung.hole(2025, 5)
        assert mai.gewichtet_cent is None
        assert mai.arithmetisch_cent == 40.0
        assert mai.abgedeckte_stunden == 24

        # Juni: nur Bezug, keine Preise ⇒ gar kein Eintrag (wie `None` im Einzelweg)
        assert messung.hole(2025, 6) is None

    @pytest.mark.asyncio
    async def test_die_randstunde_des_vormonats_faellt_nicht_in_den_maerz(self, db):
        """Die Bereichsbedingung ersetzt `extract` — die Grenzen müssen halten."""
        aid = await _bestand(db)
        maerz = (await lade_preis_aggregate_je_monat(db, aid)).hole(2025, 3)
        einzeln = await berechne_monats_durchschnittspreis(aid, 2025, 3, db)
        # 99 ct der Stunde vom 28.02. würde den arithmetischen Ø sichtbar heben.
        assert maerz.abgedeckte_stunden == 78 == einzeln.abgedeckte_stunden
        assert maerz.arithmetisch_cent < 30.0

    @pytest.mark.asyncio
    async def test_die_messung_gehoert_genau_einer_anlage(self, db):
        """Zwei Anlagen mit denselben Monaten dürfen sich nicht vermischen."""
        aid = await _bestand(db)
        fremd = await _anlage(db, "Nachbar")
        db.add_all(tep_zeilen(fremd, [
            _stunde(date(2025, 3, 1), stunde, 5.0, 1.0) for stunde in range(24)
        ]))
        await db.flush()

        eigene = await lade_preis_aggregate_je_monat(db, aid)
        fremde = await lade_preis_aggregate_je_monat(db, fremd)
        assert eigene.hole(2025, 3).gewichtet_cent == 30.0
        assert fremde.hole(2025, 3).gewichtet_cent == 5.0
        assert fremde.hole(2025, 4) is None

    @pytest.mark.asyncio
    async def test_fenster_grenzt_ein_ohne_die_werte_zu_aendern(self, db):
        """Mit Fenster kommen weniger Monate, aber dieselben Zahlen."""
        aid = await _bestand(db)
        alle = await lade_preis_aggregate_je_monat(db, aid)
        eng = await lade_preis_aggregate_je_monat(
            db, aid, von=date(2025, 4, 1), bis=date(2025, 5, 1),
        )
        assert eng.hole(2025, 3) is None
        assert eng.hole(2025, 5) is None
        assert eng.hole(2025, 4).gewichtet_cent == alle.hole(2025, 4).gewichtet_cent
        assert eng.hole(2025, 4).abgedeckte_stunden == alle.hole(2025, 4).abgedeckte_stunden


@pytest.mark.asyncio
async def test_ev_gewichteter_oe_nimmt_die_stunden_des_vermiedenen_bezugs(db):
    """A-2 (18.09.2026): Bezugs-Ø 50 ct, EV-Ø 10 ct — aus denselben Preiszeilen.

    Juli: der Bezug fällt abends (50 ct), der vermiedene Bezug mittags (10 ct).
    Die 23-Uhr-Stunde zu 70 ct trägt Einspeisung > PV und klemmt auf 0 — sie
    darf den EV-Ø nicht bewegen. Beide Wege (Einzelmonat, gruppiert) gleich.
    """
    from backend.services.strompreis_aggregator import (
        berechne_monats_durchschnittspreis, lade_preis_aggregate_je_monat,
    )
    aid = await _bestand(db)
    einzeln = await berechne_monats_durchschnittspreis(aid, 2025, 7, db)
    gruppe = (await lade_preis_aggregate_je_monat(db, aid)).hole(2025, 7)
    for agg in (einzeln, gruppe):
        assert agg.gewichtet_cent == 50.0
        assert agg.ev_gewichtet_cent == 10.0
    # Monate ohne PV-Zeilen kennen keinen EV-Ø — `None`, nicht 0.
    assert (await berechne_monats_durchschnittspreis(aid, 2025, 3, db)).ev_gewichtet_cent is None
