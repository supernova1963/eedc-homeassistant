"""Die WP-Gruppe aus Kanälen — Wahl, Leser, Gleichheit (HA-Bauform E4d, Auftrag Punkt 2 und 5, N-630).

* **Wahl** (``wp_leser.waehle_wp``, rein): ``kanal`` nur, wenn JEDER benötigte Kanal deckt; sonst ``bestand`` mit Grund.
* **Leser** am Datenstand der Achsen-Matrix (HA-Langzeitstatistik im Recorder-Schema, Spiegel, Mitschrift, abgeleiteter
  Kanal wie im Produkt): die Zeilen je Gerät in der Form einer Abschluss-Zeile.
* **Kanal-Monat ohne Abschluss == Wert nach dem Abschluss** (Bauplan §7 E-c) und **(a) nach dem Abschluss == Bestand**
  (Leser leer: gespeichert schlägt gerechnet, P8) — je Feld der WP-Feldgruppe, Toleranz 0,01 kWh (der Abschluss
  speichert auf zwei Stellen gerundet). Der Strom je Betriebsart NACH dem Abschluss kommt im gedeckten Monat aus dem
  Kanal (Abschluss-Schritt 4, ``modus_split_schreiben.kanal_split_des_monats``, Entscheid Master H-1) — ohne Deckung aus der
  Tagesebene wie bisher (eigene Probe unten).
* **ohne HA** (reine MQTT-Anlage, eigene Summe): derselbe Juni für die Formen ohne Etikett (die Mitschrift kommt aus dem
  Zustands-Verlauf von HA).
* **Cockpit → Monat** (HA-Weg, N-630): Klimagerät M06 — Heizwärme 59,4, Betriebsart-Strom 1,8/3,6, Kälte 10,8; Juni vor
  dem Abschluss alle feinen Achsen wie nach dem Abschluss (594/108/180/36/18/36/108).
* **Bestand-Lader** (Lesart 1): gedeckte Monate lädt er nicht mehr (``ohne_monate``) — die übrigen bitgleich.

Schwesterdateien: test_kanal_modus_strom.py (der Kanal), test_kanal_geraete_gleichheit.py (E-Mob/Sonstiges, Vorbild),
test_achsen_matrix.py (die Zellen als Richter).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

TOL = 0.01
FELDER = (
    "strom_kwh", "waerme_kwh", "heizung_kwh", "warmwasser_kwh", "strom_heizen_kwh", "strom_warmwasser_kwh",
    "modus_strom_heizen_kwh", "modus_strom_kuehlen_kwh", "modus_strom_warmwasser_kwh", "nutzenergie_kuehlen_kwh",
    "modus_abdeckung_h", "modus_strom_bezug_kwh", "strom_gemessen", "waerme_gemessen", "modus_gemessen",
    "modus_nicht_aufgeteilt_kwh", "modus_strom_funktionsfremd_abzug_kwh", "waerme_abgeleitet_kwh",
)


def _flach(f, ids: dict[str, int]) -> dict[str, Any]:
    rev = {v: k for k, v in ids.items()}
    w = f.wp
    out: dict[str, Any] = {k: getattr(w, k) for k in FELDER}
    for inv_id, g in (w.je_geraet or {}).items():
        out[f"geraet.{rev.get(inv_id, inv_id)}"] = (g.strom_kwh, g.waerme_kwh, g.strom_kuehlen_kwh)
    return out


def _abweichungen(a: dict, b: dict, ohne=()) -> list:
    out = []
    for k in sorted(set(a) | set(b)):
        if k in ohne:
            continue
        x, y = a.get(k), b.get(k)
        if isinstance(x, tuple) and isinstance(y, tuple):
            gleich = all(abs(p - q) <= TOL for p, q in zip(x, y))
        elif isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
            gleich = abs(x - y) <= TOL
        else:
            gleich = x == y
        if not gleich:
            out.append((k, x, y))
    return out


async def _juni(ds, *, tageswerte: bool):
    from backend.services.monats_fakten import lade_monats_fakten

    with am.umgebung(am.MATRIX_FORMEN[ds.fid], ds.svc):
        fk = await lade_monats_fakten(ds.db, ds.aid, von=(mx.JAHR, mx.JUNI), bis=(mx.JAHR, mx.JUNI),
                                      inkl_nur_tageswerte=tageswerte)
    assert fk, "der Juni fehlt"
    return _flach(fk[0], ds.ids)


# ── Wahl (rein) ─────────────────────────────────────────────────────────────


def _z(key, delta, voll=True, grund=None):
    from backend.services.kanal.lesen import Zeitraum

    return Zeitraum(key=key, art="sum", einheit="kWh", von=0, bis=1, delta=delta if voll else None,
                    teil_delta=None if voll else delta, gedeckt_von=0, gedeckt_bis=1, rand_spanne=3600, voll=voll,
                    grund=grund, laufend=False)


def test_wahl_jeder_kanal_muss_decken():
    from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key
    from backend.services.kanal.wp_leser import _Bedarf, waehle_wp

    b = _Bedarf(direkt={1: ["stromverbrauch_kwh", "waerme_kwh"]}, abgeleitet={1})
    erg = {"inv:1:stromverbrauch_kwh": _z("s", 10.0), "inv:1:waerme_kwh": _z("w", 30.0),
           modus_strom_key(1, "heizen"): _z("h", 7.0), modus_strom_key(1, "warmwasser"): _z("ww", 2.0),
           modus_strom_key(1, "kuehlen"): _z("k", 0.0), abdeckung_key(1): _z("a", 24.0)}
    w = waehle_wp(b, erg)
    assert w.kanal and w.abgeleitet == {1}
    assert w.zeilen[1] == {"stromverbrauch_kwh": 10.0, "waerme_kwh": 30.0, "modus_strom_heizen_kwh": 7.0,
                           "modus_strom_warmwasser_kwh": 2.0, "modus_strom_kuehlen_kwh": 0.0,
                           "modus_abdeckung_h": 24.0}
    erg[abdeckung_key(1)] = _z("a", 12.0, voll=False, grund="beginnt_nach_von")
    w = waehle_wp(b, erg)
    assert not w.kanal and w.wahl.gruende == {abdeckung_key(1): "beginnt_nach_von"} and not w.zeilen
    assert not waehle_wp(_Bedarf(), erg).kanal


def test_bereiche_ohne_gedeckte_monate():
    from backend.services.energie_profil.modus_split_monat import _bereiche_ohne

    assert _bereiche_ohne(None, None, frozenset()) == [(None, None)]
    assert _bereiche_ohne(None, None, frozenset({(2026, 6), (2026, 7)})) == [
        (None, date(2026, 6, 1)), (date(2026, 8, 1), None)]
    assert _bereiche_ohne(date(2026, 6, 1), date(2026, 8, 1), frozenset({(2026, 6), (2026, 7)})) == []
    assert _bereiche_ohne(date(2026, 5, 1), date(2026, 8, 1), frozenset({(2026, 6)})) == [
        (date(2026, 5, 1), date(2026, 6, 1)), (date(2026, 7, 1), date(2026, 8, 1))]


# ── Leser und Gleichheit am Datenstand ─────────────────────────────────────


async def test_leser_m06_juni_zeilen_wie_ein_abschluss():
    from backend.services.kanal.wp_leser import wp_kalendermonate, wp_monate

    async with kg.datenstand("achsen", "M06", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M06"], ds.svc):
            m = (await wp_monate(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6)))[(2026, 6)]
            k = (await wp_kalendermonate(ds.db, ds.aid, [(2026, 6)]))[(2026, 6)]
        hw, klima = ds.ids["WP HW"], ds.ids["Klima"]
        for z in (m, k):
            assert z.kanal and not z.abgeleitet                # K2: gemessene Betriebsart ⇒ kein abgeleiteter Kanal
            assert z.zeilen[hw] == pytest.approx({"strom_heizen_kwh": 180.0, "strom_warmwasser_kwh": 36.0,
                                                  "heizenergie_kwh": 540.0, "warmwasser_kwh": 108.0})
            assert z.zeilen[klima] == pytest.approx({
                "betriebsart_strom_heizen_kwh": 18.0, "betriebsart_strom_kuehlen_kwh": 36.0,
                "betriebsart_nutzenergie_heizen_kwh": 54.0, "betriebsart_nutzenergie_kuehlen_kwh": 108.0})


async def test_leser_m05_der_abgeleitete_kanal_traegt_die_aufteilung():
    from backend.services.kanal.wp_leser import wp_monate

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M05"], ds.svc):
            z = (await wp_monate(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6)))[(2026, 6)]
        wp = ds.ids["WP"]
        assert z.kanal and z.abgeleitet == {wp}
        assert z.zeilen[wp] == pytest.approx({
            "stromverbrauch_kwh": 216.0, "waerme_kwh": 648.0, "modus_strom_heizen_kwh": 198.0,
            "modus_strom_warmwasser_kwh": 18.0, "modus_strom_kuehlen_kwh": 0.0, "modus_abdeckung_h": 720.0})


@pytest.mark.parametrize("fid", ("M05", "M06", "M07"))
async def test_kanal_monat_ohne_abschluss_gleich_dem_wert_nach_dem_abschluss_und_a_bleibt_der_bestand(fid):
    async with kg.datenstand("achsen", fid, "HA") as ds:
        vor = await _juni(ds, tageswerte=True)
        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
            await am.schreibe_s1_aus_ha_laden(ds.db, am.MATRIX_FORMEN[fid], ds.aid)
        nach = await _juni(ds, tageswerte=False)
        # P8: auch MIT Tageswerten trägt der Monat mit WP-Zeile die Zeile, keine Kanal-Zeile daneben
        nach_tw = await _juni(ds, tageswerte=True)
        with patch("backend.services.kanal.wp_leser.wp_monate", new=AsyncMock(return_value={})):
            bestand = await _juni(ds, tageswerte=False)
    assert not _abweichungen(vor, nach), _abweichungen(vor, nach)
    assert not _abweichungen(nach, bestand), _abweichungen(nach, bestand)
    assert not _abweichungen(nach_tw, nach), _abweichungen(nach_tw, nach)
    # Die Probe misst etwas: Strom und Wärme sind gemessen (M07: gemessen 0).
    assert vor["strom_gemessen"] and vor["waerme_gemessen"]
    if fid == "M05":
        # H-1 (Entscheid Master): der Abschluss schreibt im gedeckten Monat den Kanal-Split — vor = nach = 198/18.
        assert (nach["modus_strom_heizen_kwh"], nach["modus_strom_warmwasser_kwh"]) == pytest.approx((198.0, 18.0))
    if fid == "M06":
        assert (vor["heizung_kwh"], vor["modus_strom_heizen_kwh"], vor["nutzenergie_kuehlen_kwh"]) == pytest.approx(
            (594.0, 18.0, 108.0))


@pytest.mark.parametrize("fid", ("M06", "M07"))
async def test_ohne_ha_die_eigene_summe_nennt_denselben_monat_ohne_abschluss(fid):
    async with kg.datenstand("achsen", fid, "HA") as ds:
        ha = await _juni(ds, tageswerte=True)
    async with kg.datenstand("achsen", fid, "MQTT") as ds:
        mqtt = await _juni(ds, tageswerte=True)
    assert not _abweichungen(ha, mqtt), _abweichungen(ha, mqtt)


async def test_cockpit_monat_klimageraet_n630():
    """N-630: Cockpit → Monat ohne Abschluss nennt die feinen WP-Achsen aus den Kanälen — laufend und im Juni vor dem
    Abschluss dieselben Zahlen wie nach dem Abschluss."""
    import backend.api.routes.aktueller_monat as am_route

    jaz = ("wp_jaz", "wp_jaz_grund", "wp_jaz_nenner_kwh", "wp_jaz_heizen", "wp_jaz_heizen_grund", "wp_jaz_kuehlen")
    async with kg.datenstand("achsen", "M06", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M06"], ds.svc):
            juli = (await am_route.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=7, db=ds.db)).model_dump()
            juni = (await am_route.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=6, db=ds.db)).model_dump()
            await am.schreibe_s1_aus_ha_laden(ds.db, am.MATRIX_FORMEN["M06"], ds.aid)
            nach = (await am_route.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=6, db=ds.db)).model_dump()
    # Die Arbeitszahlen (Abgrenzung je Funktion, Kühlstrom-Abzug im Nenner) aus derselben WP-Feldgruppe wie nach dem
    # Abschluss: 3,0 · Nenner 234 = 270 − 36 Kühlstrom · Heizen „Wärmepumpe und Klimaanlage in einer Zahl".
    assert {k: juni[k] for k in jaz} == pytest.approx({k: nach[k] for k in jaz})
    assert juni["wp_jaz_nenner_kwh"] == pytest.approx(234.0)
    klima = next(g for g in juli["wp_geraete"] if g["investition_id"] == ds.ids["Klima"])
    assert (juli["wp_heizung_kwh"], juli["wp_modus_strom_heizen_kwh"], juli["wp_modus_strom_kuehlen_kwh"],
            juli["wp_kaelte_kwh"], klima["waerme_kwh"]) == pytest.approx((59.4, 1.8, 3.6, 10.8, 5.4))
    assert (juni["wp_heizung_kwh"], juni["wp_kaelte_kwh"], juni["wp_strom_heizen_kwh"], juni["wp_strom_warmwasser_kwh"],
            juni["wp_modus_strom_heizen_kwh"], juni["wp_modus_strom_kuehlen_kwh"], juni["wp_warmwasser_kwh"]) == \
        pytest.approx((594.0, 108.0, 180.0, 36.0, 18.0, 36.0, 108.0))


async def test_gedeckte_monate_laedt_der_bestand_nicht():
    """Lesart 1: deckt die WP-Gruppe einen Monat, liest der Kanal-Leser ihn — der Modus-Lader der Tagesebene fragt ihn
    gar nicht ab (der große Posten der Übersicht, Konzept §3); die übrigen Monate bitgleich."""
    from backend.services.energie_profil import modus_split_monat as msm

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        voll = await msm.lade_modus_split_je_monat(ds.db, ds.aid)
        ohne_juni = await msm.lade_modus_split_je_monat(ds.db, ds.aid, ohne_monate=frozenset({(2026, 6)}))
        assert (2026, 6) in voll and (2026, 6) not in ohne_juni
        assert {m: s for m, s in voll.items() if m != (2026, 6)} == ohne_juni
        aufrufe: list = []
        echt = msm._lade_tages_eingaenge

        async def zaehle(db, aid, ab, vor, *, ohne_monate=frozenset()):
            aufrufe.append(ohne_monate)
            return await echt(db, aid, ab, vor, ohne_monate=ohne_monate)

        with patch.object(msm, "_lade_tages_eingaenge", zaehle), am.umgebung(am.MATRIX_FORMEN["M05"], ds.svc):
            from backend.services.monats_fakten import lade_monats_fakten

            await lade_monats_fakten(ds.db, ds.aid, von=(2026, 6), bis=(2026, 7))
        assert aufrufe and all({(2026, 6), (2026, 7)} <= set(o) for o in aufrufe), aufrufe


async def test_abschluss_schreibt_im_gedeckten_monat_den_kanal_split():
    """H-1 (Entscheid Master, Bauplan §9 B1 „Schritt 4 wird Kanal-Leser"): der Monatsabschluss schreibt den Split des
    abgeleiteten Kanals in die Gerätezeile, wenn die WP-Gruppe den Monat deckt; ohne Deckung wie bisher den der
    Tagesebene (an der Matrix-Form M05 ohne Leistungspfad: 0/0)."""
    from sqlalchemy import select

    from backend.models import InvestitionMonatsdaten
    from backend.services.energie_profil.modus_split_schreiben import schreibe_modus_split_monat

    async def _zeile(ds):
        imd = (await ds.db.execute(select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == ds.ids["WP"], InvestitionMonatsdaten.jahr == mx.JAHR,
            InvestitionMonatsdaten.monat == mx.JUNI))).scalar_one()
        await ds.db.refresh(imd)
        d = imd.verbrauch_daten
        return d.get("modus_strom_heizen_kwh"), d.get("modus_strom_warmwasser_kwh"), d.get("modus_abdeckung_h")

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M05"], ds.svc):
            await am.schreibe_s1_aus_ha_laden(ds.db, am.MATRIX_FORMEN["M05"], ds.aid)
            assert await _zeile(ds) == (198.0, 18.0, 720.0)
            with patch("backend.services.kanal.wp_leser.wp_monate", new=AsyncMock(return_value={})):
                await schreibe_modus_split_monat(ds.db, ds.aid, mx.JAHR, mx.JUNI)
                await ds.db.commit()
            assert await _zeile(ds) == (0.0, 0.0, 720.0)
            await schreibe_modus_split_monat(ds.db, ds.aid, mx.JAHR, mx.JUNI)
            await ds.db.commit()
            assert await _zeile(ds) == (198.0, 18.0, 720.0)
