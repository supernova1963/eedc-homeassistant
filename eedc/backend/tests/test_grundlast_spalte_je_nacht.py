"""Grundlast als Spalte der Tagestabelle — eine Zeile je Nacht (OB73-gif, #395).

Sein Anliegen war nicht die Zahl, sondern ein **Versuch**: „So würde man schön
sehen, was für einen Einfluss verschiedene Geräte haben — wenn man sie über
Nacht abgeschaltet lässt." Dafür braucht es den Nacht-Sockel **je Tag**; im
Tages-Gesamtverbrauch geht er unter (50 W über acht Stunden sind 0,4 kWh neben
20 kWh).

⛔ Der Kern dieser Datei ist **nicht**, dass eine Zahl ankommt, sondern dass es
dieselbe Größe ist wie in *Cockpit → Monat*: identische Formel
(`core/berechnungen/grundlast.py`) und identischer Filter (Stunden < 5, nur
`verbrauch_kw > 0`). Eine „verbesserte" Nachtdefinition an einer der beiden
Stellen wäre eine zweite Grundlast, die sich niemandem mehr erklären lässt.

Schwesterdatei: `test_grundlast.py` — dort die Formel selbst (Median,
Hochrechnung, Anteil). Hier ausschließlich das **Sourcing** und die Spalte.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import berechne_grundlast
from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.tage_werte import baue_tage_werte


async def _anlage(db) -> int:
    anlage = Anlage(anlagenname="GrundlastSpalte", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


def _stunde(aid: int, tag: date, h: int, verbrauch_kw):
    return TagesEnergieProfil(
        anlage_id=aid, datum=tag, stunde=h,
        pv_kw=0.0, verbrauch_kw=verbrauch_kw, einspeisung_kw=0.0, netzbezug_kw=0.0,
    )


@pytest.mark.asyncio
async def test_die_spalte_traegt_den_median_dieser_nacht(db):
    aid = await _anlage(db)
    tag = date(2026, 5, 10)
    # Fünf Nachtstunden, absichtlich unsortiert eingetragen — der Median ist 0,40.
    for h, kw in zip(range(5), [0.50, 0.30, 0.40, 0.45, 0.35]):
        db.add(_stunde(aid, tag, h, kw))
    await db.flush()

    tage = await baue_tage_werte(db, await db.get(Anlage, aid),
                                 date(2026, 5, 1), date(2026, 5, 31))

    assert len(tage) == 1
    assert tage[0].grundlast_kw == 0.4


@pytest.mark.asyncio
async def test_zwei_naechte_bekommen_zwei_zahlen(db):
    """Der eigentliche Zweck: der Unterschied zwischen zwei Nächten ist ablesbar.

    Genau das kann die Monats-Kachel nicht — sie nennt EINEN Median für den
    ganzen Monat, und ein über eine Nacht abgeschaltetes Gerät verschwindet darin.
    """
    aid = await _anlage(db)
    for h, kw in zip(range(5), [0.40] * 5):
        db.add(_stunde(aid, date(2026, 5, 10), h, kw))
    for h, kw in zip(range(5), [0.35] * 5):      # ein 50-W-Gerät ausgeschaltet
        db.add(_stunde(aid, date(2026, 5, 11), h, kw))
    await db.flush()

    tage = await baue_tage_werte(db, await db.get(Anlage, aid),
                                 date(2026, 5, 1), date(2026, 5, 31))

    werte = {t.datum: t.grundlast_kw for t in tage}
    assert werte[date(2026, 5, 10)] == 0.4
    assert werte[date(2026, 5, 11)] == 0.35


@pytest.mark.asyncio
async def test_der_filter_ist_woertlich_der_der_monatskachel(db):
    """Stunde 5 zählt NICHT, eine 0 zählt NICHT, ein `None` zählt NICHT.

    ⚠ Die Zahlen sind so gewählt, dass die Probe **diskriminiert** — der erste
    Entwurf tat das nicht: mit fünf Nachtwerten um 0,40 blieb der Median auch
    dann 0,40, wenn man die Tagstunden mit hineinnahm. Eine Probe, die bei
    kaputtem Filter grün bleibt, belegt nichts. Jetzt tragen nur **zwei** Werte
    die Nacht, und jede der drei Filterlockerungen verschiebt das Ergebnis
    sichtbar (unten je einzeln gegengerechnet).
    """
    aid = await _anlage(db)
    tag = date(2026, 5, 10)
    db.add(_stunde(aid, tag, 0, 0.30))
    db.add(_stunde(aid, tag, 1, 0.40))
    db.add(_stunde(aid, tag, 2, 0.0))      # gemessene 0 — kein Nacht-Sockel
    db.add(_stunde(aid, tag, 3, None))     # gar nicht gemessen
    db.add(_stunde(aid, tag, 5, 4.0))      # Tagbetrieb beginnt
    db.add(_stunde(aid, tag, 12, 6.0))
    await db.flush()

    tage = await baue_tage_werte(db, await db.get(Anlage, aid),
                                 date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].grundlast_kw == 0.35          # Median aus [0,30 · 0,40]

    # Und die Gegenrechnung je Lockerung — gegen denselben Layer, damit
    # sichtbar ist, dass die Zahl oben wirklich am Filter hängt:
    g = lambda werte: berechne_grundlast(
        nacht_verbrauch_kw=werte, gesamtverbrauch_kwh=None, tage=1).grundlast_kw
    assert g([0.0, 0.30, 0.40]) == 0.3           # die 0 mitgezählt
    assert g([0.30, 0.40, 4.0]) == 0.4           # Stunde 5 mitgezählt
    assert g([0.30, 0.40, 4.0, 6.0]) == 2.2      # beide Tagstunden mitgezählt


@pytest.mark.asyncio
async def test_ohne_nachtstunde_steht_kein_wert_da(db):
    """Total-Fall: nie gemessen ⇒ `None`. Eine 0 wäre eine Behauptung."""
    aid = await _anlage(db)
    db.add(_stunde(aid, date(2026, 5, 10), 12, 3.0))
    await db.flush()

    tage = await baue_tage_werte(db, await db.get(Anlage, aid),
                                 date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].grundlast_kw is None


@pytest.mark.asyncio
async def test_eine_einzige_nachtstunde_bleibt_stehen(db):
    """Teilabdeckung wird NICHT unterdrückt — dieselbe Grenze wie im ganzen Baum.

    Unterdrückt wird nur der Total-Fall (Test darüber). Eine Mindestzahl an
    Nachtstunden einzuführen wäre eine neue Grenze, keine angewandte
    ([[feedback_unterdruecken_nur_im_total_fall]]) — und der Monats-Pfad kennt
    sie auch nicht.
    """
    aid = await _anlage(db)
    db.add(_stunde(aid, date(2026, 5, 10), 2, 0.42))
    await db.flush()

    tage = await baue_tage_werte(db, await db.get(Anlage, aid),
                                 date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].grundlast_kw == 0.42
