"""Proben HA-Bauform S5, Etappe E-S5-4 (S5b Teil 2): **der Bestands-Tagespfad nur für Lesart 1** — Weichen und Reste
(Bauplan S5 §10j 4, 7; Nachmessung E2 A-2; E-S5-3 ⚑ A-6/A-7).

* **Wärme-Verlauf:** ``waerme_verlauf._tageswerte_je_geraet`` liest die Zählerstände (``lade_tageswerte_je_geraet``) nur
  für Tage ohne WP-Kanal-Wahl; an WP-Kanal-Tagen die Kanal-Werte — Werte gleich der Rechnung bis E-S5-4 (Zählerstände
  über den ganzen Bereich, Kanal-Werte darübergelegt).
* **A-2:** ein WP-Kanal-Tag ohne Tageszeile hat im Wärme-Verlauf seinen Bezug aus dem Kanal — derselbe Strom wie
  *Cockpit → Tag* (``tages_eingaenge``).
* **A-6:** die Alt/Neu-Tabelle der Werkbank-Vorschau (``snapshot/reaggregator``) nennt an einem Kanal-Tag keine Achse der
  Gruppen, deren Mengen der Lauf nicht schreibt (``mengen_weiche``); am Bestandstag dieselben Achsen wie bisher.
* **A-7:** die Achse-2-Diagnose nennt die Kanal-Tage des Bereichs («nichts zu vergleichen»).

Datenstand: ``kanal_bilanz_gleichheit.datenstand`` (Achsen-Formen, HA-Weg, Uhr der Matrix). Schwesterdateien:
test_s5_e3_schreiber.py (Weiche), test_n756_waerme_verlauf_kanal_tag.py, test_n757_waerme_verlauf_waerme_kanal_tag.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from backend.models import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.kanal import bilanz_leser
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 10)
VON, BIS = date(2026, 6, 1), date(2026, 6, 30)


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


async def _stamm(ds):
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    invs = {str(i.id): i for i in (await ds.db.execute(select(Investition).where(
        Investition.anlage_id == ds.aid))).scalars()}
    return anlage, invs


async def test_waerme_tageswerte_zaehlerstaende_nur_fuer_bestandstage_werte_wie_bisher(uhr, monkeypatch):
    from backend.services.energie_profil import waerme_verlauf as wv
    from backend.services.energie_profil.kanal_stunden import wp_werte_der_kanal_tage

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        anlage, invs = await _stamm(ds)
        felder = {**wv._WAERME_FELDER, **wv._KAELTE_FELDER, **wv._STROM_FELDER}
        _, rw = await wv._zaehlerstrom_je_tag(ds.db, ds.aid, VON, BIS)
        kanal = await wp_werte_der_kanal_tage(ds.db, ds.aid, invs, VON, BIS)
        assert kanal and TAG in kanal
        # bis E-S5-4: die Zählerstände über den ganzen Bereich, die Kanal-Werte darüber
        bisher = await wv.lade_tageswerte_je_geraet(ds.db, anlage, invs, VON, BIS, felder, rueckwaerts_tage=rw)
        keys = set(felder.values())
        for d, w in kanal.items():
            k = {kk: v for kk, v in w.items() if kk in keys}
            if k:
                bisher[d] = {**bisher.get(d, {}), **k}
        bereiche: list = []
        echt = wv.lade_tageswerte_je_geraet

        async def spion(db, a, i, von, bis, f, **kw):
            bereiche.append((von, bis))
            return await echt(db, a, i, von, bis, f, **kw)

        monkeypatch.setattr(wv, "lade_tageswerte_je_geraet", spion)
        neu = await wv._tageswerte_je_geraet(ds.db, anlage, invs, VON, BIS, felder, rueckwaerts_tage=rw)
    assert neu == bisher
    assert all(not (a <= d <= b) for a, b in bereiche for d in kanal)       # kein WP-Kanal-Tag im Bestands-Leser


async def test_a2_wp_kanal_tag_ohne_tageszeile_hat_den_bezug_wie_cockpit_tag(uhr):
    from backend.services.energie_profil.kanal_stunden import tages_eingaenge
    from backend.services.energie_profil.waerme_verlauf import _zaehlerstrom_je_tag, lade_waerme_verlauf

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        anlage, invs = await _stamm(ds)
        await ds.db.execute(delete(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))
        await ds.db.commit()
        je_tag, rueckwaerts = await _zaehlerstrom_je_tag(ds.db, ds.aid, VON, BIS)
        verlauf = {z.datum: z for z in await lade_waerme_verlauf(ds.db, anlage, invs, VON, BIS)}
        cockpit = (await tages_eingaenge(ds.db, anlage, invs, TAG)).wp_kwh_je_inv
    assert cockpit and je_tag[TAG] == cockpit and TAG not in rueckwaerts
    assert TAG in verlauf and verlauf[TAG].strom_kwh == round(sum(cockpit.values()), 2)


async def _ohne_kanalzeilen(ds) -> None:
    await ds.db.execute(delete(KanalStatistik).where(
        KanalStatistik.kanal_id.in_(select(Kanal.id).where(Kanal.anlage_id == ds.aid))))
    await ds.db.commit()


async def test_a6_vorschau_tabelle_nennt_an_kanal_tagen_keine_achse_der_kanal_gruppen(uhr):
    from backend.services.kanal import merken
    from backend.services.snapshot.reaggregator import get_reaggregate_preview

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        anlage, invs = await _stamm(ds)
        with kg.mx._umgebung(ds.svc):
            kanal_tag = await get_reaggregate_preview(ds.db, anlage, invs, TAG)
            await _ohne_kanalzeilen(ds)
            merken.invalidiere(ds.aid)
            bestand = await get_reaggregate_preview(ds.db, anlage, invs, TAG)
    achsen_kanal = {s["kategorie"] for s in kanal_tag["slot_deltas"]}
    achsen_bestand = {s["kategorie"] for s in bestand["slot_deltas"]}
    assert not achsen_kanal & {"pv", "einspeisung", "netzbezug", "batterie", "waermepumpe"}
    assert set(kanal_tag["tagesumme_neu"]) == achsen_kanal
    assert {"einspeisung", "netzbezug", "waermepumpe"} <= achsen_bestand


async def test_a7_achse2_diagnose_nennt_die_kanal_tage(uhr):
    from backend.api.routes.energie_profil.repair import achse2_drift_diagnose

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        r = await achse2_drift_diagnose(ds.aid, von=VON, bis=BIS, db=ds.db)
        kanal = await bilanz_leser.kanal_tage(ds.db, ds.aid, VON, BIS)
        await _ohne_kanalzeilen(ds)
        from backend.services.kanal import merken

        merken.invalidiere(ds.aid)
        ohne = await achse2_drift_diagnose(ds.aid, von=VON, bis=BIS, db=ds.db)
    assert r["kanal_tage_ohne_vergleich"] == len(kanal) == 30
    assert "nichts zu vergleichen" in r["hinweis"]
    assert ohne["kanal_tage_ohne_vergleich"] == 0 and ohne["hinweis"] is None
