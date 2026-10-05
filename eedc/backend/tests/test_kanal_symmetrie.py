"""Symmetrie-Wächter „Kanal-Δ je Tag ≡ Bestand", Familie Spiegel (HA-Bauform E2, Auftrag Punkt 6).

Auf den Datenständen beider Abnahme-Matrizen (HA-Langzeitstatistik im echten Recorder-Schema,
``achsen_matrix`` und ``pv_achse_matrix``): Spiegel aus HA nachgefüllt (``nachfuellen_spiegel``),
Tageszeilen über den echten ``aggregate_day``; dann je Anlage, Tag und ``komponenten_kwh``-Schlüssel
Tageswert gegen Kanal-Δ über das Tagesfenster ``[Vortag 23:00, 23:00)`` — seit E3 über die Lese-Schicht
(``lesen.zeitraum_stapel``) und die Fenster-Helfer (``fenster.tagesfenster``): Fenster-Helfer == Bestand. Was verglichen wird, welche
Toleranz und welche Ausnahmeklassen: ``kanal_symmetrie.py``.

**Dauerhaft:** jede Abweichung außerhalb einer benannten Klasse ist rot; jede Klasse ist gezählt und
festgehalten (``_KLASSEN_SOLL``) — wächst eine, meldet der Wächter das, statt sie still zu schlucken.

Eine Familie ``bestand`` gibt es nicht: sie bleibt unbelegt (Entscheid Gernot 06.10., Bauplan §3b) — die
bisherigen Stunden- und Tageszeilen werden nicht in Kanäle umgewandelt, der Wächter prüft den Spiegel gegen sie.

Schwesterdateien: test_kanal_nachfuellen.py, test_kanal_konsistenz.py, test_kanal_slot_umrechnung.py;
Datenstand: test_achsen_matrix.py, test_pv_achse_matrix.py.
"""

from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.kanal import Kanal, KanalStatistik
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx
from backend.tests.kanal_symmetrie import KLASSEN, symmetrie_spiegel

TAGE = mx.TAGE_JUNI + mx.TAGE_JULI


async def _lauf(matrix: str, fid: str, *, stoerung=None):
    """Seed → Nachfüllen Spiegel → Tageszeilen → Wächter. ``stoerung(sitzungen, aid)`` vor dem Vergleich."""
    verz = tempfile.mkdtemp(prefix="eedc-kanal-symmetrie-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        try:
            if matrix == "achsen":
                form = am.FORMEN[fid]
                svc, pvform = am.seed_ha(form), form.pvform
                aid, _ids = await am.seed_anlage(db, form)
                umgebung = am.umgebung(form, svc)
            else:
                pvform = mx.FORMEN[fid]
                svc = mx.seed_ha(pvform)
                aid, _ids = await mx.seed_anlage(db, pvform)
                umgebung = mx._umgebung(svc)
            with umgebung:
                erg = await nachfuellen_spiegel(sitzungen, aid, jetzt=mx.JETZT, ha_svc=svc)
                assert erg.fehler == 0 and erg.zeilen > 0
                await mx.aggregiere_tage(db, pvform, aid, TAGE)
            if stoerung is not None:
                await stoerung(sitzungen, aid)
            return await symmetrie_spiegel(db, aid)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


#: Gemessene Klassen je Form (Tag × Schlüssel), 06.10.2026 — nur was hier steht, darf ausgenommen sein.
#: ``zerlegung`` = je Tag ein PV-Schlüssel ohne eigenen Zähler (kWp-Anteil am Gesamtzähler, #406);
#: ``verworfen`` = M03 an den zwei Sprungtagen (15.06., 02.07.) je Einspeisung und PV (N-586: HAs ``sum``
#: trägt den Sprung, der Tagespfad verwirft ihn). Eine Form ohne Eintrag hat keine Ausnahme.
#: ``ohne_kanal`` = F08a/F08b am LETZTEN Tag (03.07.): der BKW-Zähler schläft 21:00–05:00, die Reihe endet am 04.07.
#: 00:00 — sein letzter Stand (21:00) erreicht das Tagesende 23:00 nicht, und es gibt keine spätere Zeile. Seit E3
#: liest der Wächter über die Lese-Schicht, und die sagt dort „deckt nicht" (Regel (b), ``endet_vor_bis``; die
#: Quellenwahl nähme den Bestand). Die E2-Hilfe rechnete den Tag still mit. Gemessen 06.10.2026.
_KLASSEN_SOLL: dict[tuple[str, str], dict[str, int]] = {
    ("achsen", "M01"): {"zerlegung": 33},
    ("achsen", "M02"): {"zerlegung": 33},
    ("achsen", "M03"): {"zerlegung": 33, "verworfen": 4},
    ("achsen", "M04"): {"zerlegung": 33},
    ("achsen", "M05"): {"zerlegung": 33},
    ("achsen", "M06"): {"zerlegung": 33},
    ("achsen", "M07"): {"zerlegung": 33},
    ("achsen", "M08"): {"zerlegung": 33},
    ("achsen", "M09"): {"zerlegung": 33},
    ("achsen", "M10"): {"zerlegung": 66},
    ("pv", "F01"): {"zerlegung": 99},
    ("pv", "F03"): {"zerlegung": 66},
    ("pv", "F04"): {"zerlegung": 66},
    ("pv", "F05"): {"zerlegung": 33},
    ("pv", "F08a"): {"ohne_kanal": 1},
    ("pv", "F08b"): {"zerlegung": 66, "ohne_kanal": 1},
    ("pv", "F09a-G"): {"zerlegung": 66},
    ("pv", "F09b-G"): {"zerlegung": 66},
    ("pv", "F09c-G"): {"zerlegung": 66},
    ("pv", "F12"): {"zerlegung": 66},
    ("pv", "F14"): {"zerlegung": 33},
}


_FORMEN = [("achsen", f) for f in am.FORMEN] + [("pv", f) for f in mx.FORMEN]


@pytest.mark.parametrize("matrix,fid", _FORMEN, ids=[f"{m}-{f}" for m, f in _FORMEN])
async def test_kanal_delta_je_tag_gleich_bestand(matrix, fid):
    b = await _lauf(matrix, fid)
    assert b.tage == len(TAGE)
    assert b.verglichen > 0, "nichts verglichen — der Wächter hätte nichts gesehen"
    assert b.abweichungen == [], b.abweichungen[:5]
    gezaehlt = {k: v for k, v in b.klassen.items() if v}
    assert set(gezaehlt) <= set(KLASSEN)
    assert gezaehlt == _KLASSEN_SOLL.get((matrix, fid), {}), gezaehlt


async def test_waechter_kann_rot_melden():
    """Gegenprobe im Test: eine Spiegelzeile um +1 kWh verschoben (ab dort alle folgenden ⇒ Δ springt
    genau an EINEM Tag) — der Wächter nennt genau diesen Tag und Schlüssel."""
    from datetime import datetime

    from backend.core.berechnungen.slot_konvention import slot_start_ts

    tag = mx.TAGE_JUNI[9]
    t = slot_start_ts(tag, 12)

    async def _stoeren(sitzungen, aid):
        async with sitzungen() as s:
            k = (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == "basis:einspeisung"))).scalar_one()
            await s.execute(update(KanalStatistik).where(KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= t)
                            .values(sum=KanalStatistik.sum + 1.0))

    b = await _lauf("achsen", "M01", stoerung=_stoeren)
    assert [(d, k) for d, k, *_ in b.abweichungen] == [(tag, "einspeisung")], b.abweichungen
    assert datetime.fromtimestamp(t).date() == tag
