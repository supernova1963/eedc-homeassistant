"""Fund N-759 (HA-Bauform S5, E-S5-4, Bauplan §10j 2): **eine PR-Stelle für alle Tage** — der Archiv-Nachzug rechnet die
Performance Ratio eines Bestandstags mit Sonstiges-Erzeuger (BHKW hinter dem Anlagenzähler) wie ``aggregate_day``.

Bis E-S5-4 suchte ``archiv_nachzug._wetterzeile_schreiben`` im Bestandszweig den Erzeuger unter ``sonstiges_<id>``; der
Schlüssel der Tageszeile ist ``sonstige_<id>`` (``core/berechnungen/energie.py::SONSTIGES_KOMPONENTEN_PREFIX``) — der Abzug
griff nie, die PR des nachgezogenen Tags enthielt die BHKW-Erzeugung. Seit E-S5-4 ruft der Nachzug für jeden Tag
``kanal_stunden.performance_ratio_des_tages`` (Kanal-Tag aus den Kanal-Stunden wie der Aggregator, Bestandstag aus den
Stundenzeilen mit Abzug über die Konstante).

Datenstand: Achsen-Form **M10** (Akku am Balkonkraftwerk, Sonstiges-Erzeuger hinter dem Zähler, Sonstiges-Verbraucher),
HA-Weg; die Kanal-Zeilen der Anlage gelöscht ⇒ der Tag ist ein Bestandstag; dieselbe Wetter-Attrappe (GTI) für den
Aggregator und den Nachzug. Schwesterdatei: test_s5_e3_schreiber.py (PR am Kanal-Tag).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, select

from backend.models import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

TAG = date(2026, 6, 10)
WETTER = {h: {"temperatur_c": 20.0, "globalstrahlung_wm2": 400.0, "gti_wm2": 450.0} for h in range(6, 20)}


async def _bestandstag_aggregiert(ds) -> TagesZusammenfassung:
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source
    from backend.services.kanal import merken

    await ds.db.execute(delete(KanalStatistik).where(
        KanalStatistik.kanal_id.in_(select(Kanal.id).where(Kanal.anlage_id == ds.aid))))
    await ds.db.commit()
    merken.invalidiere(ds.aid)
    form = am.MATRIX_FORMEN[ds.fid]
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    with am.umgebung(form, ds.svc), patch("backend.services.energie_profil._helpers._get_wetter_ist",
                                          new=AsyncMock(return_value=WETTER)):
        tz = await aggregate_day(anlage, TAG, ds.db, source=Source.SCHEDULER,
                                 prefetched_tagesverlauf=mx._kurve(form.pvform))
        await ds.db.commit()
    return tz


async def test_bestandstag_mit_sonstiges_erzeuger_nachzug_pr_gleich_aggregator_pr(monkeypatch):
    from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
    from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
    from backend.services.energie_profil.archiv_nachzug import _wetterzeile_schreiben
    from backend.services.energie_profil.kanal_stunden import kanal_stunden
    from backend.services.kanal import bilanz_leser

    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    async with kg.datenstand("achsen", "M10", "HA") as ds:
        tz = await _bestandstag_aggregiert(ds)
        assert await kanal_stunden(ds.db, ds.aid, TAG) is None          # Bestandstag
        pr_aggregator = tz.performance_ratio
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        invs = list((await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars())
        erzeuger = {i.id for i in invs if i.typ == "sonstiges" and (i.parameter or {}).get("kategorie") == "erzeuger"}
        assert erzeuger
        bhkw = sum((tz.komponenten_kwh or {}).get(f"sonstige_{i}") or 0.0 for i in erzeuger)
        assert bhkw > 0
        rows = (await ds.db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG))).scalars().all()
        kwp = anlagen_kwp(invs, TAG, mit_bkw=True, referenzwert=anlage.leistung_kwp)
        # der Wert bis E-S5-4: Σ pv_kw ohne Abzug (der Schlüssel `sonstiges_<id>` traf nie)
        pr_ohne_abzug = berechne_performance_ratio(sum(r.pv_kw for r in rows if r.pv_kw is not None), 450.0 * 14, kwp)

        tz.performance_ratio = None
        await ds.db.commit()
        assert await _wetterzeile_schreiben(anlage, TAG, WETTER, invs, erzeuger, ds.db)
        await ds.db.commit()
        nachzug = (await ds.db.execute(select(TagesZusammenfassung.performance_ratio).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
    print(f"N-759 M10 {TAG}: Aggregator-PR {pr_aggregator} · Nachzug-PR neu {nachzug} · bis E-S5-4 {pr_ohne_abzug}"
          f" (BHKW {bhkw:.3f} kWh)")
    assert pr_aggregator is not None and nachzug == pr_aggregator
    assert pr_ohne_abzug > pr_aggregator
