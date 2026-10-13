"""#110 V2H-Tageswert — Cockpit → Tag zählt die Rückspeisung des E-Autos ins Haus als Tagesgröße.

Plan: ``docs/KONZEPT-110-RESTPUNKTE.md`` §2 (E1–E3, B1–B10); Bau-Bericht ``plans/opus-berichte/V2H-TAG.md``.

**Die Regel in einem Satz:** Der Tag kennt die V2H-Rückspeisung als Tagesgröße aus dem Zählerpfad (Snapshot/MQTT und
HA-Langzeitstatistik über die eine Beitragsschicht, Tagesschlüssel ``v2h_<id>``); Stunden tragen sie nicht, einen Kanal
hat sie nicht (Katalog-Klasse „Tagesgröße ohne Kanal", ``test_kanal_feld_deckung.py``), der Monat bleibt beim Abschluss
(§2.6). In Eigenverbrauch, Gesamtverbrauch und Autarkie des Tages zählt sie genau einmal — an einem Kanal-Tag wie an
einem Tag ohne Kanal (``tagesbilanz.mit_v2h_entladung``).

Die Doubles des Bauberichts: PV 20 · Einspeisung 6 · Netzbezug 4 · Speicher 3/2 · V2H 2 ⇒ Eigenverbrauch 15,
Gesamtverbrauch 19, Autarkie 78,9 % — dieselben Zahlen wie ``berechne_verbrauchs_kennzahlen``.

Schwesterdateien: ``test_n635_eine_eigenverbrauchs_formel.py`` (die eine EV-Formel am Tag), ``test_n610_v2h_im_monat_und_vorjahr.py``
(V2H im Monat), ``test_komponenten_beitraege.py`` (Beitragsschicht), ``test_kanal_feld_deckung.py`` (Kanal-Klasse).
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace as NS
from typing import Optional

import pytest

from backend.core.berechnungen.spannen import ACHSEN, achse_der_kategorie, verbrauch_spannen_passen
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows, mit_v2h_entladung
from backend.core.berechnungen.verbrauch import berechne_verbrauchs_kennzahlen
from backend.services.snapshot.keys import _categorize_counter, _mqtt_key_to_sensor_key
from backend.services.snapshot.komponenten_beitraege import investition_beitraege, komponenten_key_label
from backend.services.snapshot.tages_tabelle import TabellenEintrag, baue_tagestabelle

V2H = "v2h_entladung_kwh"


def _auto(parameter=None, *, parent=None, inv_id=7):
    return NS(id=inv_id, typ="e-auto", bezeichnung="Privat", parameter=parameter or {},
              parent_investition_id=parent, ist_aktiv_an=lambda _d: True)


def _sensor(*felder):
    return {"felder": {f: {"strategie": "sensor", "sensor_id": f"sensor.{f}"} for f in felder}}


# ── (1) Beitragsschicht ─────────────────────────────────────────────────────


def test_v2h_traegt_eigenen_tagesschluessel_bei_v2h_faehigem_auto():
    b = investition_beitraege(_auto({"v2h_faehig": True}), _sensor(V2H, "ladung_kwh"))
    assert [(x.feld, x.target_key, x.vorzeichen) for x in b] == [
        (V2H, "v2h_7", +1), ("ladung_kwh", "eauto_7", +1),
    ]


@pytest.mark.parametrize("kw", [{"wallbox_deckt_ladung": True}, {}], ids=["wallbox_deckt", "parent"])
def test_v2h_auch_hinter_der_wallbox(kw):
    """Parent-Skip und Wallbox-Regel betreffen die LADUNG — die Rückspeisung misst nur das Auto."""
    auto = _auto({"v2h_faehig": True}, parent=None if kw else 3)
    b = investition_beitraege(auto, _sensor(V2H, "ladung_kwh"), **kw)
    assert [(x.feld, x.target_key) for x in b] == [(V2H, "v2h_7")]


def test_ohne_zuordnung_oder_ohne_v2h_faehig_kein_beitrag():
    assert all(x.feld != V2H for x in investition_beitraege(_auto({"v2h_faehig": True}), _sensor("ladung_kwh")))
    assert all(x.feld != V2H for x in investition_beitraege(_auto({}), _sensor(V2H, "ladung_kwh")))
    # Alias der Registry-Bedingung (`nutzt_v2h` → `v2h_faehig`, `bedingungen._bedingungs_werte`).
    assert any(x.target_key == "v2h_7" for x in investition_beitraege(_auto({"nutzt_v2h": True}), _sensor(V2H)))


def test_eauto_schluessel_traegt_weiter_nur_die_heimladung_und_das_label_nennt_v2h():
    b = investition_beitraege(_auto({"v2h_faehig": True}), _sensor(V2H, "ladung_kwh"))
    assert {x.feld for x in b if x.target_key == "eauto_7"} == {"ladung_kwh"}
    assert komponenten_key_label("v2h_7", _auto()) == "Privat (V2H)"
    assert komponenten_key_label("eauto_7", _auto()) == "Privat"


# ── (2) Kategorie und Achse ─────────────────────────────────────────────────


def test_kategorie_und_achse_ohne_spalte():
    assert _categorize_counter(V2H, "e-auto", {"v2h_faehig": True}) == "entladung_v2h"
    assert achse_der_kategorie("entladung_v2h") == "v2h"
    assert "v2h" in ACHSEN
    # Die Stunden-Hausverbrauchs-Regel R6 kennt die Achse nicht — eine V2H-Spanne ändert sie nicht.
    assert verbrauch_spannen_passen({"v2h": 3}, batterie_da=False)


# ── (3) Tagestabelle: Tageswert ja, Stunde nein ─────────────────────────────


def _eintraege(mit_v2h: bool) -> list[TabellenEintrag]:
    e = [
        TabellenEintrag("sensor.pv", "pv", None, "inv:1:pv_erzeugung_kwh", "pv_1", +1),
        TabellenEintrag("sensor.einsp", "einspeisung", None, "basis:einspeisung", "einspeisung", +1),
        TabellenEintrag("sensor.netz", "netzbezug", None, "basis:netzbezug", "netzbezug", +1),
    ]
    if mit_v2h:
        e.append(TabellenEintrag("sensor.v2h", "entladung_v2h", None, f"inv:7:{V2H}", "v2h_7", +1))
    return e


_SLOTS = {
    "sensor.pv": {h: (2.0, 1) for h in range(10, 20)},
    "sensor.einsp": {h: (0.6, 1) for h in range(10, 20)},
    "sensor.netz": {h: (0.5, 1) for h in (0, 1, 2, 20, 21, 22, 23, 3)},
    "sensor.v2h": {18: (1.0, 1), 19: (1.0, 1)},
}


def _tabelle(mit_v2h: bool, slots=None):
    anlage = NS(id=1, leistung_kwp=10.0)
    pv = NS(id=1, typ="pv-module", parent_investition_id=None, ist_aktiv_an=lambda _d: True,
            leistung_kwp=10.0, parameter={})
    return baue_tagestabelle(anlage, {"1": pv}, date(2026, 7, 1), _eintraege(mit_v2h), slots or _SLOTS)


def test_tagestabelle_traegt_v2h_im_rollup_und_laesst_die_stunden_unveraendert():
    ohne, mit = _tabelle(False), _tabelle(True)
    assert mit.komponenten_kwh["v2h_7"] == pytest.approx(2.0)
    assert "v2h_7" not in ohne.komponenten_kwh
    assert mit.stunden == ohne.stunden, "V2H darf in keine Stunde gehen (E2)"
    assert {k: v for k, v in mit.komponenten_kwh.items() if k != "v2h_7"} == ohne.komponenten_kwh


def test_negatives_v2h_delta_wird_auf_der_eigenen_achse_verworfen():
    slots = {**_SLOTS, "sensor.v2h": {18: (-5.0, 1), 19: (1.0, 1)}}
    t = _tabelle(True, slots)
    assert t.verworfen == {"v2h": pytest.approx(5.0)}
    assert t.komponenten_kwh["v2h_7"] == pytest.approx(1.0)


def test_mqtt_schluessel_wieder_einlesbar():
    assert _mqtt_key_to_sensor_key(f"inv/7/{V2H}") == f"inv:7:{V2H}"


# ── (4) Tagesbilanz: dieselbe Formel wie der Monat ─────────────────────────


@dataclass
class _R:
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    waermepumpe_kw: Optional[float] = None


#: Der Tag der Doubles: PV 20, Einspeisung 6, Netzbezug 4, Speicher Ladung 3 / Entladung 2.
_ROWS = [_R(pv_kw=20.0, einspeisung_kw=6.0, netzbezug_kw=4.0, batterie_kw=-3.0),
         _R(pv_kw=0.0, einspeisung_kw=0.0, netzbezug_kw=0.0, batterie_kw=2.0)]


def test_tag_mit_v2h_rechnet_wie_berechne_verbrauchs_kennzahlen():
    b = bilanz_aus_stundenrows(_ROWS, verworfen={}, v2h_entladung_kwh=2.0)
    kz = berechne_verbrauchs_kennzahlen(pv_erzeugung_kwh=20.0, einspeisung_kwh=6.0, netzbezug_kwh=4.0,
                                        speicher_ladung_kwh=3.0, speicher_entladung_kwh=2.0, v2h_entladung_kwh=2.0)
    assert b.eigenverbrauch_kwh == pytest.approx(kz.eigenverbrauch_kwh) == pytest.approx(15.0)
    assert b.gesamtverbrauch_kwh == pytest.approx(kz.gesamtverbrauch_kwh) == pytest.approx(19.0)
    assert b.autarkie_prozent == pytest.approx(kz.autarkie_prozent) == pytest.approx(78.947, abs=1e-3)
    assert b.ev_quote_prozent == pytest.approx(kz.eigenverbrauchsquote_prozent) == pytest.approx(75.0)
    assert b.v2h_entladung_kwh == 2.0 and b.verbrauch_erfasst


def test_ohne_v2h_und_mit_null_bleibt_die_bilanz_bitgleich():
    basis = bilanz_aus_stundenrows(_ROWS, verworfen={})
    assert bilanz_aus_stundenrows(_ROWS, verworfen={}, v2h_entladung_kwh=None) == basis
    assert dataclasses.replace(mit_v2h_entladung(basis, 0.0), v2h_entladung_kwh=0.0) == basis
    assert basis.eigenverbrauch_kwh == pytest.approx(13.0) and basis.gesamtverbrauch_kwh == pytest.approx(17.0)


def test_idempotent_und_genau_einmal_auch_am_gemischten_kanal_tag():
    """Kanal-Tag: die Bilanz kommt aus der Kanal-Komposition (`mische_bilanz`) — `tage_werte` wendet V2H danach an;
    Tag ohne Kanal: `bilanz_aus_stundenrows(v2h=…)`. Beide zählen V2H genau einmal, zweimal angewandt = einmal."""
    ohne_kanal = bilanz_aus_stundenrows(_ROWS, verworfen={}, v2h_entladung_kwh=2.0)
    from backend.services.kanal.bilanz_leser import mische_bilanz

    kanal = bilanz_aus_stundenrows(_ROWS, verworfen={})       # wie `bilanz_zeitraum`: Kanal-Komposition ohne V2H
    stunden = bilanz_aus_stundenrows(_ROWS, verworfen={}, v2h_entladung_kwh=2.0)
    kanal_tag = mit_v2h_entladung(mische_bilanz(kanal, stunden), 2.0)
    for b in (ohne_kanal, kanal_tag, mit_v2h_entladung(ohne_kanal, 2.0), mit_v2h_entladung(kanal_tag, 2.0)):
        assert b.eigenverbrauch_kwh == pytest.approx(15.0)
        assert b.gesamtverbrauch_kwh == pytest.approx(19.0)
    assert mit_v2h_entladung(mit_v2h_entladung(kanal_tag, 2.0), 2.0) == kanal_tag


def test_altbestand_ohne_regelmarke_bleibt_unveraendert():
    alt = bilanz_aus_stundenrows(_ROWS, verworfen=None)
    assert bilanz_aus_stundenrows(_ROWS, verworfen=None, v2h_entladung_kwh=2.0) == alt
    assert mit_v2h_entladung(alt, 2.0) is alt


def test_dieselben_sperren_wie_r7():
    # verworfen auf PV sperrt EV und Autarkie; auf der Batterie nur die Autarkie.
    pv_verw = bilanz_aus_stundenrows(_ROWS, verworfen={"pv": 1.0}, v2h_entladung_kwh=2.0)
    assert pv_verw.eigenverbrauch_kwh is None and pv_verw.autarkie_prozent is None
    assert pv_verw.gesamtverbrauch_kwh == pytest.approx(19.0)
    batt = bilanz_aus_stundenrows(_ROWS, verworfen={"batterie": 1.0}, v2h_entladung_kwh=2.0)
    assert batt.eigenverbrauch_kwh == pytest.approx(15.0) and batt.autarkie_prozent is None
    # Eine Sperre auf der eigenen V2H-Achse sperrt nichts (die Menge ist schon ohne den Rücksprung).
    v2h_verw = bilanz_aus_stundenrows(_ROWS, verworfen={"v2h": 5.0}, v2h_entladung_kwh=2.0)
    assert v2h_verw.autarkie_prozent == pytest.approx(78.947, abs=1e-3)
    # Total-Fall: ohne Netzbezug kein Gesamtverbrauch, keine Autarkie — auch nicht durch V2H.
    ohne_netz = [_R(pv_kw=20.0, einspeisung_kw=6.0)]
    t = bilanz_aus_stundenrows(ohne_netz, verworfen={}, v2h_entladung_kwh=2.0)
    assert not t.verbrauch_erfasst and t.autarkie_prozent is None
    assert t.eigenverbrauch_kwh == pytest.approx(16.0)


# ── Energieprofil → Monat: der Tagesschlüssel fließt dort nicht ein (§2.6) ──


def test_energieprofil_monat_liest_den_v2h_schluessel_nicht():
    from backend.api.routes.energie_profil._shared import _key_to_serie_info

    inv = NS(id=7, typ="e-auto", bezeichnung="Privat", parameter={})
    assert _key_to_serie_info("v2h_7", {7: inv}) is None
    assert _key_to_serie_info("eauto_7", {7: inv})["kategorie"] == "eauto"


# ── (5) Cockpit → Tag über den echten Tageslauf (HA = Kanal-Tag, Standalone = Tag ohne Kanal) ──


def _form(mit_v2h: bool):
    from backend.tests import achsen_matrix as am

    felder = {"ladung_pv_kwh": am.stunden(0.5, 12, 14), "ladung_netz_kwh": am.stunden(0.5, 20, 22)}
    if mit_v2h:
        felder[V2H] = am.stunden(0.5, 18, 20)
    return am.Form("V2H" if mit_v2h else "V2H-0", "E-Auto mit V2H", ("netz", "emob"), ("E3",),
                   geraete=(am.Geraet("Privat", "e-auto", felder, parameter={"v2h_faehig": True}),))


async def _tag_werte(mit_v2h: bool, weg: str):
    from sqlalchemy import select

    from backend.models import Anlage
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal.bilanz_leser import kanal_tage
    from backend.tests import achsen_matrix as am
    from backend.tests import pv_achse_matrix as mx

    form = _form(mit_v2h)
    tag = date(2026, 7, 1)
    verz = tempfile.mkdtemp(prefix="eedc-v2h-test-")
    try:
        engine, db = await mx._neue_db(f"{verz}/{weg}.db")
        try:
            aid, ids = await am.seed_anlage(db, form)
            svc = am.seed_ha(form) if weg == "HA" else mx._ha_aus()
            if weg == "SA":
                await am.seed_snapshots(db, form, aid, ids)
            with am.umgebung(form, svc):
                if weg == "HA":
                    await mx.fuelle_spiegel(engine, aid, svc)
                await mx.aggregiere_tage(db, form.pvform, aid, [tag])
                anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
                z = (await baue_tage_werte(db, anlage, tag, tag))[0]
                ist_kanal = tag in await kanal_tage(db, aid, tag, tag)
            return z, ist_kanal
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("weg, kanal", [("HA", True), ("SA", False)], ids=["HA-Kanal-Tag", "Standalone-ohne-Kanal"])
async def test_cockpit_tag_zaehlt_v2h_genau_einmal(weg, kanal):
    mit, ist_kanal = await _tag_werte(True, weg)
    ohne, _ = await _tag_werte(False, weg)
    assert ist_kanal is kanal, "die Probe muss beide Tagesarten treffen"
    assert ohne.v2h_entladung is None
    assert mit.v2h_entladung == pytest.approx(1.0)          # 0,5 kWh × 2 Stunden
    assert mit.erzeugung == ohne.erzeugung and mit.netzbezug == ohne.netzbezug
    assert mit.eigenverbrauch == pytest.approx(ohne.eigenverbrauch + 1.0)
    assert mit.gesamtverbrauch == pytest.approx(ohne.gesamtverbrauch + 1.0)
    assert mit.autarkie == pytest.approx(
        round((mit.gesamtverbrauch - mit.netzbezug) / mit.gesamtverbrauch * 100, 1), abs=0.05)
    assert mit.ev_ersparnis > ohne.ev_ersparnis, "die Finanzzeile bewertet dieselbe Menge"
