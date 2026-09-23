"""Die vollständige Kaskade des Monats-Netzbezugspreises (#412, 11.09.2026).

Schwesterdateien: `test_monatsabschluss_feld_dyn_tarif.py` (wann der Anwender
den gepflegten Wert überhaupt eintragen kann), `test_zeittarif_ht_nt.py`
(Stufe 3), `test_aggregatoren_und_verbrauchsprognose.py` (der Aggregator hinter
Stufe 2), `test_cockpit_ev_ersparnis_flex_326.py` (ein Leser der Auflösung).

**Der Gegenstand.** `resolve_netzbezug_preis_cent` kannte zwei Stufen —
gepflegt, sonst Tarif. Wer einen dynamischen Tarif hat, sah deshalb in
*Cockpit → Tag* und im **laufenden** Monat den festen Tarifpreis, obwohl eedc
die Stundenpreise mitschreibt und im Monatsabschluss längst einen Ø daraus
vorschlägt (OB73-gif, #412). Die Zahl war nicht falsch gerechnet — sie war die
schlechtere von zwei verfügbaren.

⛔ **Die Nicht-Entscheidung, die hier mitgeprüft wird:** Es gibt **keine**
Mindestabdeckung. Ein erster Entwurf sah eine vor; sie hätte genau den Fall
ausgeschlossen, für den sie gedacht war (s. `test_keine_mindestabdeckung`).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.models import Anlage, Strompreis
from backend.models.monatsdaten import Monatsdaten
from backend.models.strompreis import StrompreisZeitfenster
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.tests.slot_saat import tep_zeilen
from backend.services.strompreis_aggregator import (
    PREIS_HERKUNFT_GEMESSEN,
    PREIS_HERKUNFT_GEPFLEGT,
    PREIS_HERKUNFT_STAMM,
    PREIS_HERKUNFT_ZEITFENSTER,
    aufgeloester_monatspreis,
)

JAHR, MONAT = 2026, 6


async def _anlage(db, *, vertragsart=None, nachtfenster=False) -> tuple[int, Strompreis]:
    """Anlage + Tarif, **über den Produktivweg geladen**.

    ⚠ Der Tarif wird nach dem Anlegen über ``lade_tarife_fuer_anlage`` neu
    geholt und nicht als frisches ORM-Objekt weitergereicht. Das ist kein
    Umstand, sondern der Gegenstand: ``hat_zeitfenster`` liest die
    Relationship ``zeitfenster``, und die trägt ``lazy="selectin"`` genau
    deshalb, weil ein Lazy-Load in der AsyncSession mit ``MissingGreenlet``
    abbricht (Kommentar an `models/strompreis.py:75`). Eine Fixture, die den
    Ladeweg umgeht, prüft einen Zustand, den die Produktion nicht kennt —
    beim Bau genau so aufgetreten.
    """
    anlage = Anlage(anlagenname="Preis", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    tarif = Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2025, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        vertragsart=vertragsart,
    )
    db.add(tarif)
    await db.flush()
    if nachtfenster:
        # Nachttarif 22–06 Uhr zu 20 ct, außerhalb die 30 ct der Spalte.
        db.add(StrompreisZeitfenster(
            strompreis_id=tarif.id, von_stunde=22, bis_stunde=6,
            wochentage="0123456", arbeitspreis_cent_kwh=20.0,
        ))
        await db.flush()
    tarife = await lade_tarife_fuer_anlage(db, anlage.id, target_date=date(JAHR, MONAT, 1))
    return anlage.id, tarife["allgemein"]


async def _stundenpreise(db, anlage_id: int, *, tage: int, preis: float, bezug: float):
    """`tage` Tage à 24 **Stunden** mit demselben Preis und Netzbezug.

    ⭐ **N-387: der Preis einer Stunde steht in der Zeile davor** (Menge
    backward, Preis forward) — `tep_zeilen` verteilt ihn, für die Stunde 0 des
    ersten Tages also in die letzte Zeile des Vormonats. Die Aussage der Proben
    ist unverändert: **alle** gesäten Stunden tragen Preis und Menge.
    """
    db.add_all(tep_zeilen(anlage_id, [
        {"datum": date(JAHR, MONAT, tag), "stunde": stunde,
         "strompreis_cent": preis, "netzbezug_kw": bezug}
        for tag in range(1, tage + 1)
        for stunde in range(24)
    ]))
    await db.flush()


class TestDieVierStufen:
    @pytest.mark.asyncio
    async def test_1_gepflegt_schlaegt_alles(self, db):
        """Der abgerechnete Wert gewinnt — eedc misst, der Versorger berechnet."""
        anlage_id, tarif = await _anlage(db)
        await _stundenpreise(db, anlage_id, tage=30, preis=22.0, bezug=1.0)
        md = Monatsdaten(
            anlage_id=anlage_id, jahr=JAHR, monat=MONAT,
            netzbezug_durchschnittspreis_cent=26.5,
        )

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, md, tarif)

        assert p.cent == 26.5
        assert p.herkunft == PREIS_HERKUNFT_GEPFLEGT

    @pytest.mark.asyncio
    async def test_1b_ein_gepflegter_nullpreis_ist_ein_wert(self, db):
        """⚠ Die 0-Werte-Falle: 0,0 ct ist bei dynamischem Tarif real (viele
        Negativpreis-Stunden) und darf nicht als „nichts gepflegt" gelten."""
        anlage_id, tarif = await _anlage(db)
        md = Monatsdaten(
            anlage_id=anlage_id, jahr=JAHR, monat=MONAT,
            netzbezug_durchschnittspreis_cent=0.0,
        )

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, md, tarif)

        assert p.cent == 0.0
        assert p.herkunft == PREIS_HERKUNFT_GEPFLEGT

    @pytest.mark.asyncio
    async def test_2_ohne_gepflegten_wert_gilt_die_messung(self, db):
        """**Der Fall des Melders.** Kein Abschluss, aber Stundenpreise."""
        anlage_id, tarif = await _anlage(db)
        await _stundenpreise(db, anlage_id, tage=30, preis=22.0, bezug=1.0)

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        assert p.cent == pytest.approx(22.0)
        assert p.herkunft == PREIS_HERKUNFT_GEMESSEN
        assert p.abdeckung == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_2b_die_messung_ist_verbrauchsgewichtet(self, db):
        """Nicht das arithmetische Mittel: teure Stunden zählen so viel, wie in
        ihnen bezogen wurde."""
        anlage_id, tarif = await _anlage(db)
        db.add_all(tep_zeilen(anlage_id, [
            {"datum": date(JAHR, MONAT, 1), "stunde": stunde,
             "strompreis_cent": 40.0 if stunde < 6 else 20.0,
             "netzbezug_kw": 3.0 if stunde < 6 else 1.0}
            for stunde in range(24)
        ]))
        await db.flush()

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        # (6×3×40 + 18×1×20) / (6×3 + 18×1) = 1080/36 = 30,0
        assert p.cent == pytest.approx(30.0)
        assert p.herkunft == PREIS_HERKUNFT_GEMESSEN

    @pytest.mark.asyncio
    async def test_4_ohne_stundenpreise_bleibt_der_stammpreis(self, db):
        anlage_id, tarif = await _anlage(db)

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        assert p.cent == 30.0
        assert p.herkunft == PREIS_HERKUNFT_STAMM
        assert p.abdeckung is None


class TestDieReihenfolgeIstEineAussage:
    @pytest.mark.asyncio
    async def test_die_messung_schlaegt_das_zeitfenster(self, db):
        """⭐ **Wo beides vorliegt, gewinnt der BEZAHLTE Preis.**

        Ein Anwender mit HT/NT-Fenstern **und** zugeordnetem Preissensor ist vom
        Datenmodell nicht ausgeschlossen. Der gemessene Endpreis ist das, was
        durch den Zähler ging; der zeitgewichtete ist eine Rechnung über den
        Tarif.
        """
        anlage_id, tarif = await _anlage(db, nachtfenster=True)
        await _stundenpreise(db, anlage_id, tage=30, preis=18.0, bezug=1.0)

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        assert p.herkunft == PREIS_HERKUNFT_GEMESSEN
        assert p.cent == pytest.approx(18.0)

    @pytest.mark.asyncio
    async def test_ohne_messung_greift_das_zeitfenster(self, db):
        """Gegenprobe — Stufe 3 ist nicht tot, sie steht nur hinter Stufe 2."""
        anlage_id, tarif = await _anlage(db, nachtfenster=True)
        # Netzbezug ohne Preis-Spalte: für die Messung unbrauchbar, für die
        # Zeitfenster-Gewichtung genau die richtige Reihe.
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=date(JAHR, MONAT, 1), stunde=stunde,
                netzbezug_kw=1.0,
            ))
        await db.flush()

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        assert p.herkunft == PREIS_HERKUNFT_ZEITFENSTER
        assert p.cent != 30.0, "sonst hätte die Gewichtung nichts getan"


class TestKeineMindestabdeckung:
    @pytest.mark.asyncio
    async def test_keine_mindestabdeckung(self, db):
        """⛔ **Die Nicht-Entscheidung, und warum sie so herum fällt.**

        `abdeckung` misst gegen den **vollen** Monat (`sollstunden =
        tage_im_monat * 24`). Am 11. eines 30-Tage-Monats sind höchstens 36 %
        erreichbar. Jede Schwelle ab 50 % hätte den **laufenden** Monat bis nach
        Monatsmitte auf den Stammpreis zurückgeworfen — also genau den Fall
        ausgeschlossen, für den sie gedacht war.

        Stattdessen: Der Wert gilt, die Abdeckung steht daneben (P4 — *„der Wert
        wird nicht ersetzt, nur beschriftet"*).
        """
        anlage_id, tarif = await _anlage(db)
        await _stundenpreise(db, anlage_id, tage=3, preis=19.0, bezug=1.0)

        p = await aufgeloester_monatspreis(db, anlage_id, JAHR, MONAT, None, tarif)

        assert p.herkunft == PREIS_HERKUNFT_GEMESSEN
        assert p.cent == pytest.approx(19.0)
        assert p.abdeckung is not None and p.abdeckung < 0.15, (
            "72 von 720 Stunden — die Zahl gilt, sagt aber ihre Abdeckung"
        )


class TestCache:
    @pytest.mark.asyncio
    async def test_der_cache_liefert_dasselbe_ergebnis(self, db):
        anlage_id, tarif = await _anlage(db)
        await _stundenpreise(db, anlage_id, tage=30, preis=22.0, bezug=1.0)
        cache: dict = {}

        erst = await aufgeloester_monatspreis(
            db, anlage_id, JAHR, MONAT, None, tarif, cache=cache,
        )
        nochmal = await aufgeloester_monatspreis(
            db, anlage_id, JAHR, MONAT, None, tarif, cache=cache,
        )

        assert erst == nochmal
        assert list(cache) == [(JAHR, MONAT)]
