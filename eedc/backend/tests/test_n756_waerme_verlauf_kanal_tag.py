"""N-756 (H-4, HA-Bauform S4-Nachlauf) — der Wärme-Verlauf (Tagesreihe der Route ``waerme-verlauf``, dieselben Leser für die
Wärme-Verteilung und die Tagesebene-Mengen von Cockpit → Monat) nennt an einem Kanal-Tag denselben Tag wie Cockpit → Tag.

**Befund (HEAD 0a4e852e, gemessen 17.10.2026, Messskript ``plans/ha-bauform-werkzeug/fund-s4-nachlauf/wv_messung.py``):**
``waerme_verlauf._zaehlerstrom_je_tag`` nahm den WP-Strom aus ``TagesZusammenfassung.komponenten_kwh`` (Bestands-Fenster
[Vortag 23:00, 23:00)) und setzte die Rückwärts-Tage nur aus der Tageszeile; Wärme und Betriebsart-Zähler liefen damit auch
an Kanal-Tagen rückwärts. Seit E-S4-1 liegt Cockpit → Tag an einem Kanal-Tag im Kalendertag ⇒ der Wärme-Verlauf stand um
die Stunde 23–24 Uhr daneben (30.06.: 7,2/21,6 statt 8,2/24,6; Σ Juni 216/648 statt 217/651). Vor S4 waren beide rückwärts.

**Regel seit dem Bau:** dieselben Weichen wie ``kanal_stunden.tages_eingaenge`` — Bilanz-Kanal-Tag ⇒ Bilanz-Schlüssel aus
dem Kanal (``mische_komponenten``), WP-Kanal-Tag ⇒ ``waermepumpe_<id>`` aus dem Kanal-Stundentag
(``kanal_stunden.wp_komponenten_der_kanal_tage``); beide Tage im Kalendertag. Bestandstage bleiben rückwärts.

Form: Achsen-Matrix M05 (WP 0,3 kWh/h Strom, 0,9 kWh/h Wärme), am 30.06. 23–24 Uhr zusätzlich 1,0 kWh Strom und 3,0 kWh
Wärme. Uhr 04.07.2026 00:30.

Schwesterdateien: ``test_n754_netzladung_kanal_tag.py`` (N-754, dieselbe Klasse, Speicher-Netzladung), ``test_n435_tages_jaz_ein_fenster.py``.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from datetime import date, datetime

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

TAGE = am.TAGE_JUNI + am.TAGE_JULI
RAND = datetime(2026, 6, 30, 23)


def _form() -> am.Form:
    m05 = am.MATRIX_FORMEN["M05"]
    felder = {"stromverbrauch_kwh": lambda t: 0.3 + (1.0 if t == RAND else 0.0),
              "waerme_kwh": lambda t: 0.9 + (3.0 if t == RAND else 0.0)}
    return dataclasses.replace(m05, fid="H4", geraete=(dataclasses.replace(m05.geraete[0], felder=felder),))


def _r(x):
    return None if x is None else round(x, 2)


async def _messe(weg: str) -> dict:
    """Je Tag Cockpit → Tag (Tagesliste ``wp_strom``, ``tag-detail`` ``wp_waerme_kwh``) und Wärme-Verlauf; Cockpit → Monat."""
    import backend.api.routes.aktueller_monat as amr
    from sqlalchemy import select

    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.models import Anlage, Investition
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.energie_profil.waerme_verlauf import lade_waerme_verlauf

    form = _form()
    verz = tempfile.mkdtemp(prefix="eedc-h4-")
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
                await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                await mx.baue_abgeleitete_nach_tagen(engine, aid)
                anlage = await db.get(Anlage, aid)
                invs = {str(i.id): i for i in (await db.execute(
                    select(Investition).where(Investition.anlage_id == aid))).scalars().all()}
                tw = {z.datum: z for z in await baue_tage_werte(db, anlage, TAGE[0], TAGE[-1])}
                tag = {t: (_r(tw[t].wp_strom), _r((await get_tag_detail(anlage_id=aid, datum=t, db=db)).wp_waerme_kwh))
                       for t in TAGE}
                verlauf = {}
                for von, bis in ((date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 3))):
                    verlauf.update({z.datum: (_r(z.strom_kwh), _r(z.waerme_kwh))
                                    for z in await lade_waerme_verlauf(db, anlage, invs, von, bis)})
                monat = {}
                for m in (6, 7):
                    c = await amr.get_aktueller_monat(anlage_id=aid, jahr=2026, monat=m, db=db)
                    monat[m] = (_r(c.wp_strom_kwh), _r(c.wp_waerme_kwh))
            return {"tag": tag, "verlauf": verlauf, "monat": monat}
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


def _summe(werte: dict, monat: int) -> tuple:
    return tuple(round(sum(v[i] or 0.0 for t, v in werte.items() if t.month == monat), 2) for i in (0, 1))


async def test_kanal_tage_verlauf_wie_cockpit_tag_und_monat():
    """HA-Spiegel (Kanal-Tage): 30.06. 8,2/24,6, 01.07. 7,2/21,6 in Tagesliste UND Verlauf; Σ Juni 217/651, Σ Juli
    21,6/64,8 — gleich Cockpit → Monat. Bis zum Bau nannte der Verlauf 7,2/21,6 · 8,2/24,6 und Σ 216/648 · 22,6/67,8."""
    m = await _messe("HA")
    assert m["tag"][date(2026, 6, 30)] == (8.2, 24.6) and m["tag"][date(2026, 7, 1)] == (7.2, 21.6)
    assert m["verlauf"] == m["tag"], {t: (m["tag"][t], m["verlauf"].get(t)) for t in TAGE
                                       if m["tag"][t] != m["verlauf"].get(t)}
    assert (_summe(m["verlauf"], 6), _summe(m["verlauf"], 7)) == ((217.0, 651.0), (21.6, 64.8))
    assert (m["monat"][6], m["monat"][7]) == ((217.0, 651.0), (21.6, 64.8))


async def test_bestandstage_bleiben_rueckwaerts():
    """Gegenprobe ohne Kanäle (Standalone, Bestandstage): Tagesliste und Verlauf rückwärts und gleich — die Randstunde
    des 30.06. steht am 01.07."""
    m = await _messe("SA")
    assert m["verlauf"] == m["tag"]
    assert m["verlauf"][date(2026, 6, 30)] == (7.2, 21.6) and m["verlauf"][date(2026, 7, 1)] == (8.2, 24.6)
