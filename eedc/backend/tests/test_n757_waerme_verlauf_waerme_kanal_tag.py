"""N-757 (HA-Bauform S4-Nachlauf) — Wärme, Kälte und Funktions-Achsen des Wärme-Verlaufs und der Wärme-Verteilung an einem
Kanal-Tag aus dem Kanal-Stundentag, wie *Cockpit → Tag*.

**Befund (HEAD 2c66b88d, gemessen 17.10.2026, Messskript ``plans/ha-bauform-werkzeug/fund-s4-nachlauf/w2_messung.py``):**
seit E-S4-1 nimmt *Cockpit → Tag* an einem WP-Kanal-Tag Wärme und Funktions-Achsen aus dem Kanal (``kanal_stunden.
tages_eingaenge`` → ``detail_aus_kanaelen``); Wärme-Verlauf und Wärme-Verteilung lasen sie weiter aus den Zählerständen
(``lade_tageswerte_je_geraet``). Wo beide auseinanderlaufen (der Spiegel kennt etwas, was die Stände nicht kennen — eine
Korrektur in HA, HAs Lückenregel, ein verworfenes Feld), nannte der Verlauf eine andere Wärme als der Tag und die
Monats-Verteilung leere Segmente (Kanal-Kopie, Anlage 1, 23.04.2026: Verlauf 15,65 gegen Tag 12,61 = Kanal-Δ). Bis S4 lasen
beide die Stände (gleich).

**Regel seit dem Bau** (``waerme_verlauf._tageswerte_je_geraet`` → ``kanal_stunden.wp_werte_der_kanal_tage``, dieselbe
Auswahl ``kanal_werte_je_inv`` wie ``detail_aus_kanaelen``): an einem WP-Kanal-Tag aus dem Kanal-Stundentag, sonst aus den
Zählerständen.

Form: Achsen-Matrix M06, nur ``WP HW`` (getrennte Strommessung, Heiz-/Warmwasser-Wärme), HA-Weg. Nach dem Spiegeln
weichen die Zählerstände (HA-Statistik) vom Spiegel ab: ab 15.06. 12:00 + 5,0 kWh Heizwärme und + 2,0 kWh Strom Heizen —
der Spiegel kennt das nicht. Uhr 04.07.2026 00:30.

Schwesterdateien: ``test_n756_waerme_verlauf_kanal_tag.py`` (N-756, der Strom), ``test_waerme_verlauf_bereichs_leser.py``.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
import time as _zeit
from datetime import date, datetime

import pytest
from sqlalchemy import text

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

TAGE = am.TAGE_JUNI + am.TAGE_JULI
SPRUNG_AB = datetime(2026, 6, 15, 12)
TAG = date(2026, 6, 15)


def _form() -> am.Form:
    """M06 nur mit ``WP HW`` — das Klimagerät mit Betriebsart-Nutzenergie Heizen trüge N-493 (archiviert: die Wärme-Linie
    kennt sie nicht) in den Vergleich."""
    m06 = am.MATRIX_FORMEN["M06"]
    return dataclasses.replace(m06, fid="N757", geraete=(m06.geraet("WP HW"),))


def _r(x):
    return None if x is None else round(x, 2)


def _staende_weichen_ab(svc, form) -> None:
    """Die HA-Statistik (Quelle der Zählerstände) bekommt nach dem Spiegeln einen Sprung, den der Spiegel nicht kennt."""
    wp = form.geraet("WP HW")
    ab = _zeit.mktime(SPRUNG_AB.timetuple())
    with svc._engine.begin() as conn:
        for feld, kwh in (("heizenergie_kwh", 5.0), ("strom_heizen_kwh", 2.0)):
            conn.execute(text("UPDATE statistics SET sum = sum + :k, state = state + :k WHERE start_ts >= :ab AND "
                              "metadata_id = (SELECT id FROM statistics_meta WHERE statistic_id = :sid)"),
                         {"k": kwh, "ab": ab, "sid": wp.sid(feld)})


async def _messe(weg: str) -> dict:
    import backend.api.routes.aktueller_monat as amr
    from sqlalchemy import select

    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.api.routes.energie_profil.waerme import get_waerme_verteilung
    from backend.models import Anlage, Investition
    from backend.services.energie_profil.waerme_verlauf import lade_waerme_verlauf

    form = _form()
    verz = tempfile.mkdtemp(prefix="eedc-n757-")
    try:
        engine, db = await mx._neue_db(f"{verz}/{weg}.db")
        try:
            aid, ids = await am.seed_anlage(db, form)
            svc = am.seed_ha(form) if weg == "HA" else mx._ha_aus()
            if weg != "HA":
                await am.seed_snapshots(db, form, aid, ids)
            with am.umgebung(form, svc):
                if weg == "HA":
                    await mx.fuelle_spiegel(engine, aid, svc)
                    _staende_weichen_ab(svc, form)
                await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                await mx.baue_abgeleitete_nach_tagen(engine, aid)
                anlage = await db.get(Anlage, aid)
                invs = {str(i.id): i for i in (await db.execute(
                    select(Investition).where(Investition.anlage_id == aid))).scalars().all()}
                tag = {t: _r((await get_tag_detail(anlage_id=aid, datum=t, db=db)).wp_waerme_kwh) for t in am.TAGE_JUNI}
                verlauf = {z.datum: _r(z.waerme_kwh) for z in await lade_waerme_verlauf(
                    db, anlage, invs, date(2026, 6, 1), date(2026, 6, 30))}
                vt = (await get_waerme_verteilung(anlage_id=aid, sicht="tag", jahr=None, monat=None, datum=TAG, db=db))
                vm = (await get_waerme_verteilung(anlage_id=aid, sicht="monat", jahr=2026, monat=6, datum=None, db=db))
                vm = vm.model_dump() if hasattr(vm, "model_dump") else vm
                vt = vt.model_dump() if hasattr(vt, "model_dump") else vt
                periode = next(p for p in vm["perioden"] if p["schluessel"] == TAG.isoformat())
                c = await amr.get_aktueller_monat(anlage_id=aid, jahr=2026, monat=6, db=db)
            return {"tag": tag, "verlauf": verlauf, "monat": _r(c.wp_waerme_kwh),
                    "segmente_tag": {s["schluessel"]: _r(s["kwh"]) for s in vt["segmente"]},
                    "segmente_monat_15": {k: _r(v) for k, v in periode["kwh_je_segment"].items()}}
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def test_kanal_tage_waerme_und_achsen_wie_cockpit_tag():
    """HA-Spiegel (Kanal-Tage), Zählerstände mit einem Sprung, den der Spiegel nicht kennt: der Verlauf nennt an jedem Tag die
    Wärme von Cockpit → Tag, Σ Juni = Cockpit → Monat; die Monats-Verteilung trägt am 15.06. dieselben Segmente wie die
    Tagessicht. Bis zum Bau nannte der Verlauf am 15.06. die Zählerstände (5,0 kWh mehr) und die Segmente den Strom Heizen
    der Stände."""
    m = await _messe("HA")
    assert m["verlauf"] == m["tag"], {t: (m["tag"][t], m["verlauf"].get(t)) for t in m["tag"] if m["tag"][t] != m["verlauf"].get(t)}
    assert round(sum(v for v in m["verlauf"].values() if v is not None), 2) == m["monat"]
    assert m["segmente_monat_15"] and m["segmente_monat_15"] == {
        k: v for k, v in m["segmente_tag"].items() if k in m["segmente_monat_15"]}, (m["segmente_monat_15"], m["segmente_tag"])


async def test_bestandstage_unveraendert():
    """Gegenprobe ohne Kanäle (Standalone, Bestandstage): Verlauf = Cockpit → Tag aus den Zählerständen, wie vor dem Bau."""
    m = await _messe("SA")
    assert m["verlauf"] == m["tag"]
