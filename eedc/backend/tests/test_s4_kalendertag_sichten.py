"""HA-Bauform S4, Etappe E-S4-1 — die Sichten am Kalendertag (Auftrag Punkt 4, Bauplan S4 §10a).

* **Monat** (4a): Heatmap, Tagesprofil und Spitzen nennen für BEIDE Zeilenarten die Stunde des Beginns
  (``slot_konvention.stundenbeginn_der_zeile``: Bestandszeile ``s`` ⇒ ``(s−1) mod 24``, Mischzeile ``h`` ⇒ ``h``); der
  Grundbedarf bleibt an der Zeilen-Stunde (Bestand Slots 0–4, Mischzeile Stunden 0–4).
* **Tag** (4b): an einem Kanal-Tag kommen WP-Strom je Gerät, Wärme/Kälte, gemessene Betriebsart und der Modus-Split
  bzw. die E-Mob-PV-Ladung aus dem Kanal-Stundentag (Σ Stunden ≡ Tages-Δ, S3-R4) — ``kanal_stunden.tages_eingaenge``,
  die EINE Umschaltstelle von ``tag-detail`` und den Wärme-Sichten; «ohne Stundenform» ist dort 0.
* **tage-werte** (4d): Grundlast aus den Mischzeilen, Sonstiges aus dem Tages-Δ der Sonstiges-Gruppe.
* **/stunden** (4e): ``raster`` je Zeile — Bestandstag ``"ende"``, Kanal-Tag ``"beginn"``.

Datenstände: Achsen-Formen (``kanal_bilanz_gleichheit.datenstand``, HA), Tag 15.06.2026, Uhr der Matrix gestellt.
Schwesterdateien: test_kanal_stunden_sichten.py, test_n444_tagesdetail_ein_fenster.py, test_kanal_slot_umrechnung.py.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.kanal import bilanz_leser
from backend.services.kanal.stunden_leser import kanal_stundentag
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 15)


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


def _summe(werte) -> float:
    return sum(v for v in werte if v is not None)


# ── 4a: Monat ───────────────────────────────────────────────────────────────


def test_monat_stunde_des_beginns_fuer_beide_zeilenarten():
    from backend.api.routes.energie_profil.monat import _Stunden, _stunde_sammeln

    st = _Stunden()
    bestand = SimpleNamespace(datum=TAG, stunde=0, pv_kw=0.0, verbrauch_kw=0.5, einspeisung_kw=0.0, netzbezug_kw=0.5,
                              spannen=None)
    misch = SimpleNamespace(datum=TAG, stunde=0, raster="beginn", pv_kw=0.0, verbrauch_kw=0.7, einspeisung_kw=0.0,
                            netzbezug_kw=0.7, spannen=None)
    _stunde_sammeln(st, bestand)
    _stunde_sammeln(st, misch)
    assert [z.stunde for z in st.heatmap] == [23, 0]                       # Slot 0 beginnt um 23:00
    assert st.profil_verbrauch[23] == [0.5] and st.profil_verbrauch[0] == [0.7]
    assert [p.stunde for p in st.netzbezug_kandidaten] == [23, 0]
    assert st.nacht_verbrauch == [0.5, 0.7]                               # Grundbedarf an der Zeilen-Stunde


async def test_monat_antwort_nennt_das_raster_beginn(uhr):
    from backend.api.routes.energie_profil.views import get_monatsauswertung

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        m = await get_monatsauswertung(ds.aid, TAG.year, TAG.month, 10, ds.db)
    assert m.raster == "beginn"
    assert sorted({z.stunde for z in m.heatmap if z.tag == TAG.day}) == list(range(24))


# ── 4b: Tag und Wärme-Sichten ───────────────────────────────────────────────


async def _eingaenge(ds):
    from backend.services.energie_profil.kanal_stunden import tages_eingaenge

    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    invs = {str(i.id): i for i in (await ds.db.execute(
        select(Investition).where(Investition.anlage_id == ds.aid))).scalars().all()}
    return await tages_eingaenge(ds.db, anlage, invs, TAG), await kanal_stundentag(ds.db, ds.aid, TAG,
                                                                                    jetzt=kg.JETZT_TS)


async def test_tag_wp_aus_dem_kanal_stundentag_getrennte_strommessung_und_betriebsart(uhr):
    """M06: getrennte Strommessung Heizen/Warmwasser (Gerät A) + Klima mit Betriebsart-Zählern (Gerät B) — jeder
    Tageswert ist die Σ der Stunden seines Kanals."""
    async with kg.datenstand("achsen", "M06", "HA") as ds:
        e, st = await _eingaenge(ds)
        a, b = str(ds.ids["WP HW"]), str(ds.ids["Klima"])
    wp = st.gruppen["wp"]
    s = {k: _summe(m) for k, m in wp.mengen.items()}
    assert e.kanal_tag and e.wp_aus_kanal
    assert e.detail.werte["wp_strom_heizen_kwh"] == pytest.approx(s[f"inv:{a}:strom_heizen_kwh"])
    assert e.detail.werte["wp_strom_warmwasser_kwh"] == pytest.approx(s[f"inv:{a}:strom_warmwasser_kwh"])
    assert e.detail.werte["wp_heizung_kwh"] == pytest.approx(s[f"inv:{a}:heizenergie_kwh"])
    assert e.detail.werte["wp_kaelte_kwh"] == pytest.approx(s[f"inv:{b}:betriebsart_nutzenergie_kuehlen_kwh"])
    assert e.gemessen_je_inv[b] == pytest.approx({"betriebsart_strom_heizen_kwh": s[f"inv:{b}:betriebsart_strom_heizen_kwh"],
                                                  "betriebsart_strom_kuehlen_kwh": s[f"inv:{b}:betriebsart_strom_kuehlen_kwh"]})
    assert e.wp_kwh_je_inv[a] == pytest.approx(s[f"inv:{a}:strom_heizen_kwh"] + s[f"inv:{a}:strom_warmwasser_kwh"])


async def test_tag_modus_split_aus_den_abgeleiteten_kanaelen_und_waerme_ohne_stundenform_null(uhr):
    """M05: Gesamtstrom + Wärmezähler, Betriebsart als Etikett — der Modus-Split des Tages faltet die abgeleiteten
    Kanäle «Strom je Betriebsart» auf den Kanal-Strom; die Wärme-Sicht liegt auf dem Beginn-Raster und hat keine Menge
    ohne Stundenform (Balken = Kanal)."""
    from backend.api.routes.energie_profil.waerme import get_waerme_verlauf_stunden

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        e, st = await _eingaenge(ds)
        w = await get_waerme_verlauf_stunden(anlage_id=ds.aid, datum=TAG, db=ds.db)
        wp_id = str(ds.ids["WP"])
    strom = _summe(st.gruppen["wp"].mengen[f"inv:{wp_id}:stromverbrauch_kwh"])
    assert e.wp_kwh_je_inv[wp_id] == pytest.approx(strom)
    split = e.splits[wp_id]
    abdeckung = _summe(st.gruppen["wp"].mengen[f"abgeleitet:inv:{wp_id}:modus_abdeckung_h"])
    assert split.bezug_kwh == pytest.approx(strom)
    assert split.abdeckung_h == pytest.approx(abdeckung) and 0 < split.abdeckung_h <= 24   # Stunden, nicht × Betriebsarten
    assert sum(split.kwh_je_modus.values()) <= strom + 1e-6
    assert w.raster == "beginn"
    assert w.ohne_stundenform_kwh is None and w.waerme_ohne_stundenform_kwh is None
    assert _summe(z.wp_strom_kwh for z in w.stunden) == pytest.approx(strom, abs=0.002)


async def test_tag_emob_pv_ladung_aus_dem_kanal(uhr):
    """M09: E-Auto ohne Wallbox mit PV-/Netz-Ladung — die Tagesdetail-Werte der E-Mob-Gruppe sind die Kanal-Δ."""
    async with kg.datenstand("achsen", "M09", "HA") as ds:
        e, st = await _eingaenge(ds)
    emob = st.gruppen.get("emob")
    assert emob is not None and e.emob_aus_kanal
    verglichen = 0
    for feld, aus in (("ladung_pv_kwh", "emob_ladung_pv_kwh"), ("ladung_netz_kwh", "emob_ladung_netz_kwh")):
        kanaele = [k for k in emob.mengen if k.startswith("inv:") and k.endswith(":" + feld)]
        if kanaele:
            assert e.detail.werte.get(aus) == pytest.approx(sum(_summe(emob.mengen[k]) for k in kanaele)), aus
            verglichen += 1
    assert verglichen == 2


# ── 4d: tage-werte ─────────────────────────────────────────────────────────


async def test_tage_werte_sonstiges_und_grundlast_am_kanal_tag(uhr):
    """M07: Sonstiges mit Alt- und Neuname — Verbrauch des Tages = Δ des Sonstiges-Kanals über den Kalendertag;
    Grundlast aus den Mischzeilen (Stunden 0–4 des Kalendertags)."""
    from backend.api.routes.energie_profil.tage import get_tage_werte
    from backend.core.berechnungen import berechne_grundlast
    from backend.services.energie_profil.kanal_stunden import stunden_der_kanal_tage

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        _e, st = await _eingaenge(ds)
        zeile = {z.datum: z for z in await get_tage_werte(ds.aid, TAG, TAG, ds.db)}[TAG]
        misch = (await stunden_der_kanal_tage(ds.db, ds.aid, [TAG], {}))[TAG]
    sonst = st.gruppen["sonstiges"]
    assert zeile.sonstiges_verbrauch == pytest.approx(sum(_summe(m) for m in sonst.mengen.values()), abs=0.01)
    nacht = [float(r.verbrauch_kw) for r in misch if r.stunde < 5 and (r.verbrauch_kw or 0) > 0]
    assert zeile.grundlast_kw == berechne_grundlast(nacht_verbrauch_kw=nacht, gesamtverbrauch_kwh=None, tage=1).grundlast_kw


# ── 4e: /stunden ───────────────────────────────────────────────────────────


async def test_stunden_raster_ende_am_bestandstag(db):
    from backend.api.routes.energie_profil.views import get_stundenwerte
    from backend.models.tages_energie_profil import TagesEnergieProfil

    a = Anlage(anlagenname="Bestand", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    for h in range(24):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=TAG, stunde=h, pv_kw=1.0, source_provenance={}))
    await db.commit()
    antwort = await get_stundenwerte(anlage_id=a.id, datum=TAG, db=db)
    assert [s.stunde for s in antwort.stunden] == list(range(24))
    assert {s.raster for s in antwort.stunden} == {"ende"}


async def test_stunden_raster_beginn_am_kanal_tag(uhr):
    from backend.api.routes.energie_profil.views import get_stundenwerte

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        antwort = await get_stundenwerte(anlage_id=ds.aid, datum=TAG, db=ds.db)
    assert {s.raster for s in antwort.stunden} == {"beginn"}
