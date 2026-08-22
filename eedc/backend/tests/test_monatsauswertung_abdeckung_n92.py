"""Die Monats-KPIs erben die Abdeckung ihrer Summanden (N-92, 2026-08-22).

`get_monatsauswertung` ist der **Zwilling** von
`core/berechnungen/tagesbilanz.py` — sein Modul-Docstring sagt ausdrücklich, er
trage dessen NULL-Semantik 1:1. Für die Summen stimmte das; für die beiden aus
ihnen gebildeten **Differenzen** nicht:

* ``eigenverbrauch_prozent`` steht auf ``pv_sum - einspeisung_sum``
* ``autarkie_prozent``       steht auf ``verbrauch_sum - netzbezug_sum``

Beide waren nur gegen einen **leeren Nenner** geschützt, nicht gegen einen
Summanden mit anderer Abdeckung. Regel-SoT:
``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §3 Regel 1 — *„Eine Differenz erbt die
Unvollständigkeit jedes Summanden."*

⚠ **Warum dieser Test hier steht und nicht nur am Layer:** die Stelle ist eine
**zweite** Implementierung derselben Formel (N-129-Klasse). Ein Test allein am
Layer hätte die Route nicht gehalten — und genau so ist die Drift zwischen
beiden Pfaden schon einmal entstanden.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.energie_profil.views import get_monatsauswertung
from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil


def _stunde(aid: int, tag: date, h: int, *, pv=None, vb=None, ei=None, nz=None):
    return TagesEnergieProfil(
        anlage_id=aid, datum=tag, stunde=h,
        pv_kw=pv, verbrauch_kw=vb, einspeisung_kw=ei, netzbezug_kw=nz,
        batterie_kw=None, waermepumpe_kw=None,
    )


async def _anlage(db, rows_fn) -> int:
    anlage = Anlage(anlagenname="N92-Abdeckung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add_all(rows_fn(anlage.id))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_einspeisung_teilabgedeckt_unterdrueckt_die_ev_quote(db):
    """PV über 8 Stunden, Einspeisung nur über 6 ⇒ die Quote ist keine Aussage.

    Ohne die Regel meldete der Endpunkt eine EV-Quote, die um genau die zwei
    nicht gemessenen Einspeisungsstunden zu hoch war — ohne jeden Hinweis.
    """
    tag = date(2026, 5, 10)

    def rows(aid):
        r = [_stunde(aid, tag, h, pv=2.0, ei=1.0) for h in range(8, 14)]
        r += [_stunde(aid, tag, h, pv=2.0) for h in (14, 15)]
        return r

    aid = await _anlage(db, rows)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    # Die additiven Summen bleiben unberührt — sie sind richtungssicher.
    assert monat.pv_kwh == 16.0
    assert monat.einspeisung_kwh == 6.0
    # Die Differenz-Quote nicht.
    assert monat.eigenverbrauch_prozent is None


@pytest.mark.asyncio
async def test_netzbezug_nie_gemessen_unterdrueckt_die_autarkie(db):
    """Verbrauch gemessen, Netzbezug nirgends ⇒ nicht „100 % Autarkie".

    Dieselbe Lage wie Strikers Januar (T89667 #162). Der Tages-Prognose-Pfad
    schützt sich seit A28 ausdrücklich dagegen (`views.py`, „würde dann aber
    ‚Netzbezug 0, Autarkie 100 %' behaupten") — dieser Pfad tat es nicht.
    """
    tag = date(2026, 5, 11)

    def rows(aid):
        return [_stunde(aid, tag, h, vb=1.0, ei=2.0) for h in range(8, 16)]

    aid = await _anlage(db, rows)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert monat.verbrauch_kwh == 8.0      # die Summe bleibt
    assert monat.netzbezug_kwh == 0.0
    assert monat.autarkie_prozent is None  # 100.0 wäre der Befund


@pytest.mark.asyncio
async def test_volle_abdeckung_liefert_beide_quoten_unveraendert(db):
    """Gegenprobe: die Regel darf den Normalfall NICHT verschieben.

    Enthält bewusst eine Stunde mit **gemessenen Nullen** auf beiden Achsen —
    eine 0 ist eine Aussage und muss eine Zahl bleiben.
    """
    tag = date(2026, 5, 12)

    def rows(aid):
        r = [_stunde(aid, tag, h, pv=4.0, vb=1.0, ei=3.0, nz=0.0) for h in range(9, 15)]
        r += [_stunde(aid, tag, 22, pv=0.0, vb=1.0, ei=0.0, nz=1.0)]
        return r

    aid = await _anlage(db, rows)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert monat.pv_kwh == 24.0
    assert monat.verbrauch_kwh == 7.0
    assert monat.autarkie_prozent is not None
    assert monat.eigenverbrauch_prozent is not None
