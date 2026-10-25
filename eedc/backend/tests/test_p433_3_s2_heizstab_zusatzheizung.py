"""P-433-3 Sitzung 2 (#432) — Heizstab-Zähler und «AZ ohne Zusatzheizung» in Tag, Hub und Monatstabelle.

Bauplan ``bauplan-p433-3-temperaturen-heizstab-tagessicht.md`` Fassung 2, S2-1 … S2-3 (E-P3-4/5/9):

* **S2-1 Registry** — ``heizstab_strom_kwh`` «Strom Zusatzheizung» (kWh, kumulativ, ``betriebsart: geraet``, ohne
  Bedingung), automatisch in ``KUMULATIVE_ZAEHLER_FELDER``, Ausgabe ``wp_heizstab_kwh`` der Tagesdetail-Tabelle,
  **kein** Bilanzbeitrag (Teilmenge des Gerätestroms, Konvention H-B — keine Doppelzählung).
* **S2-2 Layer** — ``arbeitszahl_ohne_zusatzheizung(system, heizstab_kwh)``: Zähler und Nenner der Hauptzahl je um
  den Heizstab-Strom gekürzt (Wirkungsgrad 1); Kühlstrom-Abzug und Sperren geerbt.
* **S2-3 Mengen** — Tag (``tag-detail``), Hub (Kennzahl + ``jaz_je_monat``), Monats-Fakten (``WpFakten.heizstab_kwh``)
  — und **keine** Wirkung auf Strom, Wärme, Ersparnis, CO₂, Community-Payload oder HA-Sensoren (B8): je Sicht die
  Probe «Summen unverändert», gemessen an derselben Anlage vor und nach dem Eintrag des Heizstab-Werts.

Die Mathek-Lage (#432): 26 kWh Wärme, 6 kWh Strom, davon 0,4 kWh Heizstab ⇒ JAZ 4,33, ohne Zusatzheizung
25,6 ÷ 5,6 = 4,571.

Schwesterdatei: ``test_p433_3_s1_live_temperaturen.py`` (Sitzung 1: Live-Felder, Überblick, Checker).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDSTROM,
    GRUND_KLASSE_AUSSTATTUNG,
    GRUND_WAERME_NICHT_GROESSER_ALS_ZUSATZHEIZUNG,
    GRUND_ZUSATZHEIZUNG_GROESSER_ALS_STROM,
    HANDGRIFF_JE_GRUND,
    HEIZSTAB_HINWEIS,
    HINWEIS_OHNE_ZUSATZHEIZUNG,
    arbeitszahl,
    arbeitszahl_ohne_zusatzheizung,
    grund_klasse,
    systemarbeitszahl,
)
from backend.core.field_definitions import (
    FELD_EINHEITEN,
    INVESTITION_FELDER,
    WP_BETRIEBSART_GERAET,
    get_feld_bedarf,
    get_felder_fuer_investition,
)
from backend.core.field_definitions.karten import wp_menge
from backend.models import Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.snapshot.aggregator import (
    TAGESDETAIL_AUSGABE,
    WAERME_AUSGABE_KEYS,
    WP_STROM_AUSGABE_ZU_FELD,
)
from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER, _categorize_counter
from backend.services.snapshot.komponenten_beitraege import investition_beitraege
from backend.tests.test_bs6_kaelte_je_tag import DATUM as TAG_DATUM
from backend.tests.test_bs6_kaelte_je_tag import _tageszaehler, _tageszeile
from backend.tests.test_r2_je_funktion import JAHR, MONAT, _anlage, _geraet, _monat

FELD = "heizstab_strom_kwh"
AUSGABE = "wp_heizstab_kwh"
#: Eine Luft-Wasser-WP ohne getrennte Strommessung — der Gesamtzähler ist die Menge (K3).
_WP_GESAMT = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"}
#: Die Mathek-Lage als Monatszeile (× 100, damit die Hub-Rundung auf 0,1 kWh nichts verdeckt).
MONAT_OHNE = {"stromverbrauch_kwh": 600.0, "waerme_kwh": 2600.0}
HEIZSTAB_MONAT = 40.0

#: Die neuen Schlüssel je Sicht — alles andere muss bitgleich bleiben.
NEU_HUB = {
    "gesamt_heizstab_kwh", "jaz_ohne_zusatzheizung", "jaz_ohne_zusatzheizung_grund",
    "jaz_ohne_zusatzheizung_hinweis", "jaz_ohne_zusatzheizung_zaehler_kwh", "jaz_ohne_zusatzheizung_nenner_kwh",
}
NEU_JAZ_MONAT = {
    "heizstab_kwh", "ohne_zusatzheizung_wert", "ohne_zusatzheizung_grund",
    "ohne_zusatzheizung_zaehler_kwh", "ohne_zusatzheizung_nenner_kwh",
}
NEU_TAG = {
    "wp_heizstab_kwh", "wp_jaz_ohne_zusatzheizung", "wp_jaz_ohne_zusatzheizung_grund",
    "wp_jaz_ohne_zusatzheizung_hinweis", "wp_jaz_ohne_zusatzheizung_zaehler_kwh",
    "wp_jaz_ohne_zusatzheizung_nenner_kwh",
}


def _registry_feld() -> dict:
    (f,) = [f for f in INVESTITION_FELDER["waermepumpe"] if f["feld"] == FELD]
    return f


# ═══ S2-1 Registry ═══════════════════════════════════════════════════════════

def test_feld_am_geraet_ohne_bedingung():
    f = _registry_feld()
    assert (f["label"], f["einheit"], FELD_EINHEITEN[FELD]) == ("Strom Zusatzheizung", "kWh", "kWh")
    assert f["betriebsart"] == WP_BETRIEBSART_GERAET
    assert f["csv_suffix"] == "Strom_Zusatzheizung_kWh"
    assert "bedingung" not in f and "weich" not in f, "P13 — an jeder Wärmepumpe zuordenbar"
    assert get_feld_bedarf("waermepumpe", FELD)[0] == "optional"
    # Der Hinweis nennt die Konvention und den HA-Helfer (S2-1).
    assert "HINTER dem Stromzähler" in f["hinweis"] and "Integral" in f["hinweis"]


@pytest.mark.parametrize("wp_art", ["luft_wasser", "sole_wasser", "grundwasser", "luft_luft", "brauchwasser"])
def test_an_jeder_bauart_im_monatsabschluss(wp_art):
    felder = {f["feld"] for f in get_felder_fuer_investition("waermepumpe", {"wp_art": wp_art})}
    assert FELD in felder, wp_art


def test_automatisch_kumulativer_zaehler_und_tagesausgabe():
    """W2/G2: die Zählerliste ist aus der Registry abgeleitet — die Tagesmenge braucht den Eintrag der Tabelle."""
    assert FELD in KUMULATIVE_ZAEHLER_FELDER["waermepumpe"]
    assert TAGESDETAIL_AUSGABE[("waermepumpe", FELD)] == AUSGABE
    assert AUSGABE not in WAERME_AUSGABE_KEYS, "Strom ist keine Wärme-Linie"
    assert AUSGABE not in WP_STROM_AUSGABE_ZU_FELD, "K3 entscheidet ohne den Heizstab"


def test_kein_bilanzbeitrag_teilmenge_des_geraetestroms():
    """H-B: der Heizstab hängt hinter dem WP-Zähler — als Beitrag stünde sein Strom doppelt in der Bilanz.

    Sprengsatz-Ziel des Nachmessers: ``_categorize_counter`` liefert für das Feld ``verbrauch_wp`` ⇒ diese Probe rot,
    und die Stundenbilanz läge um den Heizstab über dem Tageswert.
    """
    assert _categorize_counter(FELD, "waermepumpe", dict(_WP_GESAMT)) is None
    assert _categorize_counter(FELD, "waermepumpe", {"getrennte_strommessung": True}) is None

    class _Inv:
        id, typ, parameter = 7, "waermepumpe", dict(_WP_GESAMT)

    mapping = {"felder": {
        "stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"},
        FELD: {"strategie": "sensor", "sensor_id": "sensor.heizstab"},
    }}
    assert [b.feld for b in investition_beitraege(_Inv(), mapping)] == ["stromverbrauch_kwh"]
    nur_heizstab = {"felder": {FELD: {"strategie": "sensor", "sensor_id": "sensor.heizstab"}}}
    assert investition_beitraege(_Inv(), nur_heizstab) == []
    # Keine Mengenart: im Datenquellen-Block «Gerät gesamt» deckt er den Gerätestrom nicht (sonst «fehlt: Strom» bzw.
    # «vollständig» allein durch den Heizstab-Zähler — Client-Probe `datenquellenBetriebsart.test.ts`, Mathek).
    assert wp_menge(FELD) is None


# ═══ S2-2 Layer ══════════════════════════════════════════════════════════════

def test_mathek_26_6_0_4():
    sys = systemarbeitszahl(26.0, 6.0)
    az = arbeitszahl_ohne_zusatzheizung(sys, 0.4)
    assert sys.wert == pytest.approx(26 / 6)
    assert az.wert == pytest.approx(25.6 / 5.6) and round(az.wert, 3) == 4.571
    assert (az.zaehler_kwh, az.nenner_kwh) == (pytest.approx(25.6), pytest.approx(5.6))
    assert az.hinweis == HINWEIS_OHNE_ZUSATZHEIZUNG and az.grund is None


def test_kuehlstrom_abzug_wird_geerbt():
    """Ü9/G6: der Nenner ist der der Hauptzahl (6 − 1 Kühlstrom), nicht der Rohstrom — Sprengsatz-Ziel."""
    sys = systemarbeitszahl(26.0, 6.0, kuehlstrom_kwh=1.0)
    az = arbeitszahl_ohne_zusatzheizung(sys, 0.4)
    assert sys.nenner_kwh == pytest.approx(5.0)
    assert az.nenner_kwh == pytest.approx(4.6)
    assert az.zaehler_kwh == pytest.approx(25.6)
    assert az.wert == pytest.approx(25.6 / 4.6)


def test_fremdstrom_sperrt_beide():
    sys = systemarbeitszahl(26.0, 6.0, abgrenzung_verletzt=GRUND_FREMDSTROM)
    az = arbeitszahl_ohne_zusatzheizung(sys, 0.4)
    assert sys.wert is None and az.wert is None
    assert az.grund == sys.grund == GRUND_FREMDSTROM


def test_die_geraete_arbeitszahl_ist_derselbe_eingang():
    """Der Hub reicht die Geräte-JAZ (``arbeitszahl``) herein — dieselbe Rechnung, dieselbe Zahl."""
    az = arbeitszahl_ohne_zusatzheizung(arbeitszahl(26.0, 6.0), 0.4)
    assert az.wert == pytest.approx(25.6 / 5.6)


@pytest.mark.parametrize("heizstab", [6.0, 7.5])
def test_zusatzheizung_groesser_als_der_geraetestrom(heizstab):
    az = arbeitszahl_ohne_zusatzheizung(systemarbeitszahl(26.0, 6.0), heizstab)
    assert az.wert is None and az.grund == GRUND_ZUSATZHEIZUNG_GROESSER_ALS_STROM


def test_waerme_nicht_groesser_als_die_zusatzheizung():
    az = arbeitszahl_ohne_zusatzheizung(systemarbeitszahl(3.0, 6.0), 4.0)
    assert az.wert is None and az.grund == GRUND_WAERME_NICHT_GROESSER_ALS_ZUSATZHEIZUNG


def test_eine_schranke_wird_keine_ausweis_zahl():
    """P4: ein «≥» hat an einer ``Arbeitszahl`` kein Zeichen — die Zahl entfällt mit dem Satz der Schranke."""
    sys = systemarbeitszahl(26.0, 6.0, strom_ohne_waerme_kwh=1.0, geraete_ohne_waerme=["Klima"])
    assert sys.ist_schranke
    az = arbeitszahl_ohne_zusatzheizung(sys, 0.4)
    assert az.wert is None and az.grund == sys.schranke_hinweis


def test_ohne_hauptzahl_derselbe_grund_und_negativer_heizstab_wird_geklemmt():
    ohne_strom = systemarbeitszahl(26.0, None)
    assert arbeitszahl_ohne_zusatzheizung(ohne_strom, 0.4).grund == ohne_strom.grund
    sys = systemarbeitszahl(26.0, 6.0)
    assert arbeitszahl_ohne_zusatzheizung(sys, -1.0).wert == pytest.approx(sys.wert)


def test_heizstab_hinweis_bleibt_woertlich_und_gilt_der_zweiten_zahl_nicht():
    """B3/Ü8: der H-B-Satz ist zitiert (Handbuch, Konzept, Wächter) — die Ausweis-Zahl trägt ihren eigenen."""
    assert HEIZSTAB_HINWEIS == (
        "Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt "
        "elektrisch erzeugt wurde (Heizstab, Zusatz- oder Notheizung). Die Zahl "
        "beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."
    )
    sys = systemarbeitszahl(9.0, 6.0)  # 1,5 < Schwelle ⇒ die Hauptzahl trägt den H-B-Satz
    assert sys.hinweis == HEIZSTAB_HINWEIS
    assert arbeitszahl_ohne_zusatzheizung(sys, 2.0).hinweis == HINWEIS_OHNE_ZUSATZHEIZUNG


def test_beide_gruende_sind_ausstattung_mit_handgriff():
    for g in (GRUND_ZUSATZHEIZUNG_GROESSER_ALS_STROM, GRUND_WAERME_NICHT_GROESSER_ALS_ZUSATZHEIZUNG):
        assert grund_klasse(g) == GRUND_KLASSE_AUSSTATTUNG and HANDGRIFF_JE_GRUND[g]


# ═══ S2-3 Monat: eine Lesetür, Monats-Fakten ═════════════════════════════════

def test_imd_typ_beitrag_liest_den_heizstab_und_trennt_null_von_fehlt():
    class _Inv:
        typ, parameter = "waermepumpe", dict(_WP_GESAMT)

    ohne = imd_typ_beitrag(_Inv(), dict(MONAT_OHNE))
    mit = imd_typ_beitrag(_Inv(), {**MONAT_OHNE, FELD: HEIZSTAB_MONAT})
    null = imd_typ_beitrag(_Inv(), {**MONAT_OHNE, FELD: 0.0})
    assert (ohne.wp_heizstab, ohne.wp_heizstab_gemessen) == (0.0, False)
    assert (mit.wp_heizstab, mit.wp_heizstab_gemessen) == (HEIZSTAB_MONAT, True)
    assert (null.wp_heizstab, null.wp_heizstab_gemessen) == (0.0, True)
    # Teilmenge: Strom und Wärme der Zeile bleiben, was sie waren.
    assert (mit.wp_strom, mit.wp_waerme) == (ohne.wp_strom, ohne.wp_waerme)


async def _lage(db, daten: dict, name: str = "P433-3 S2"):
    a = await _anlage(db, name)
    inv = await _geraet(db, a, "WP", dict(_WP_GESAMT), dict(daten))
    await db.commit()
    return a, inv


async def _heizstab_eintragen(db, inv, kwh: float) -> None:
    md = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == inv.id)
    )).scalars().one()
    md.verbrauch_daten = {**(md.verbrauch_daten or {}), FELD: kwh}
    flag_modified(md, "verbrauch_daten")
    await db.commit()


@pytest.mark.asyncio
async def test_monats_fakten_tragen_den_heizstab_und_sonst_nichts_neues(db):
    a, inv = await _lage(db, MONAT_OHNE)
    (vorher,) = await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)
    (nachher,) = await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))

    assert vorher.wp.heizstab_kwh is None
    assert nachher.wp.heizstab_kwh == pytest.approx(HEIZSTAB_MONAT)
    from dataclasses import replace
    assert nachher.wp.geraete_mit_heizstab == {inv.id} and vorher.wp.geraete_mit_heizstab == frozenset()
    assert replace(nachher.wp, heizstab_kwh=None, geraete_mit_heizstab=frozenset()) == vorher.wp, (
        "Teilmenge — keine andere WP-Größe bewegt sich")
    assert replace(nachher, wp=vorher.wp) == vorher, "Ersparnis, CO₂, Finanzen des Monats unverändert"


# ═══ S2-3 Hub: Kennzahl neben der JAZ, Monatstabelle, Summen unverändert ═════

async def _hub(db, anlage_id) -> dict:
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    (g,) = await get_waermepumpe_dashboard(anlage_id, strompreis_cent=30.0, db=db)
    return g.model_dump()


@pytest.mark.asyncio
async def test_hub_zeigt_die_ausweis_zahl_mit_herleitung(db):
    a, inv = await _lage(db, MONAT_OHNE)
    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)

    z = (await _hub(db, a.id))["zusammenfassung"]

    assert z["durchschnitt_cop"] == pytest.approx(round(2600 / 600, 2)), "H-B bleibt die Hauptzahl"
    assert z["gesamt_heizstab_kwh"] == pytest.approx(40.0)
    assert z["jaz_ohne_zusatzheizung"] == pytest.approx(round(2560 / 560, 2)) == 4.57
    assert (z["jaz_ohne_zusatzheizung_zaehler_kwh"], z["jaz_ohne_zusatzheizung_nenner_kwh"]) == (2560.0, 560.0)
    assert z["jaz_ohne_zusatzheizung_hinweis"] == HINWEIS_OHNE_ZUSATZHEIZUNG
    assert z["jaz_ohne_zusatzheizung_grund"] is None
    (zeile,) = z["jaz_je_monat"]
    assert zeile["heizstab_kwh"] == pytest.approx(40.0)
    assert zeile["ohne_zusatzheizung_wert"] == 4.57
    assert (zeile["ohne_zusatzheizung_zaehler_kwh"], zeile["ohne_zusatzheizung_nenner_kwh"]) == (
        pytest.approx(2560.0), pytest.approx(560.0))


@pytest.mark.asyncio
async def test_hub_summen_unveraendert_und_ohne_zaehler_kein_schluessel(db):
    a, inv = await _lage(db, MONAT_OHNE)
    vorher = await _hub(db, a.id)
    assert not NEU_HUB & set(vorher["zusammenfassung"]), "ohne Heizstab-Zähler kein neuer Schlüssel (B2)"
    assert not NEU_JAZ_MONAT & set(vorher["zusammenfassung"]["jaz_je_monat"][0])

    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)
    nachher = await _hub(db, a.id)

    zn = {k: v for k, v in nachher["zusammenfassung"].items() if k not in NEU_HUB}
    zn["jaz_je_monat"] = [{k: v for k, v in r.items() if k not in NEU_JAZ_MONAT} for r in zn["jaz_je_monat"]]
    assert zn == vorher["zusammenfassung"], "Strom, Wärme, JAZ, Kosten, Ersparnis, CO₂ bitgleich"
    assert nachher["monatsreihe"] == vorher["monatsreihe"]
    for k in ("ersparnis_euro", "co2_ersparnis_kg", "wp_kosten_euro", "gesamt_stromverbrauch_kwh"):
        assert nachher["zusammenfassung"][k] == vorher["zusammenfassung"][k], k


@pytest.mark.asyncio
async def test_cockpit_monat_ha_sensoren_und_community_unveraendert(db):
    """B8: nichts Neues reist in HA-Sensoren und Community; Cockpit → Monat bleibt, wie es war."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.services.community_service import prepare_community_data
    from backend.tests.test_n441_geraete_identitaet import _community_anlage, _monatswert

    anlage_id = await _community_anlage(db, [dict(MONAT_OHNE)])
    inv = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, Investition.typ == "waermepumpe")
    )).scalars().one()

    async def _alles():
        sensoren = [(s.definition.key, s.value) for s in await calculate_investition_sensors(db, inv, None)]
        community = _monatswert(await prepare_community_data(db, anlage_id))
        # Nacharbeit: Cockpit → Monat trägt die sechs neuen Felder — alles andere bleibt bitgleich.
        monat = (await _monat(db, anlage_id)).model_dump(exclude={"aktualisiert_um", *NEU_TAG})
        return sensoren, community, monat

    vorher = await _alles()
    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)
    nachher = await _alles()

    assert nachher[0] == vorher[0], "HA-Sensoren bitgleich"
    assert nachher[1] == vorher[1], "Community-Monatswert bitgleich"
    assert nachher[2] == vorher[2], "Cockpit → Monat bitgleich"
    assert not any("heizstab" in k or "zusatzheizung" in k for k, _ in nachher[0])
    assert not any("heizstab" in k or "zusatzheizung" in k for k in nachher[1])


# ═══ S2-3 Tag: tag-detail ════════════════════════════════════════════════════

async def _tag_lage(db, *, heizstab: float | None):
    a = await _anlage(db, "P433-3 S2 Tag")
    a.sensor_mapping = {"investitionen": {}}
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=dict(_WP_GESAMT),
    )
    db.add(inv)
    await db.flush()
    _tageszaehler(db, a, inv, "stromverbrauch_kwh", 6.0)
    _tageszaehler(db, a, inv, "waerme_kwh", 26.0)
    if heizstab is not None:
        _tageszaehler(db, a, inv, FELD, heizstab)
    _tageszeile(db, a, {inv.id: 6.0})
    a.sensor_mapping = dict(a.sensor_mapping)
    await db.commit()
    return a


async def _tag(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_tag_detail

    return await get_tag_detail(anlage_id, TAG_DATUM, db)


@pytest.mark.asyncio
async def test_tag_mathek(db):
    a = await _tag_lage(db, heizstab=0.4)
    t = await _tag(db, a.id)

    assert t.wp_jaz == pytest.approx(26 / 6)
    assert t.wp_heizstab_kwh == pytest.approx(0.4)
    assert t.wp_jaz_ohne_zusatzheizung == pytest.approx(25.6 / 5.6)
    assert (t.wp_jaz_ohne_zusatzheizung_zaehler_kwh, t.wp_jaz_ohne_zusatzheizung_nenner_kwh) == (
        pytest.approx(25.6), pytest.approx(5.6))
    assert t.wp_jaz_ohne_zusatzheizung_grund is None
    assert t.wp_jaz_ohne_zusatzheizung_hinweis == HINWEIS_OHNE_ZUSATZHEIZUNG


@pytest.mark.asyncio
async def test_tag_ohne_zaehler_alles_leer_und_summen_unveraendert(db):
    ohne = (await _tag(db, (await _tag_lage(db, heizstab=None)).id)).model_dump()
    mit = (await _tag(db, (await _tag_lage(db, heizstab=0.4)).id)).model_dump()

    assert all(ohne[k] is None for k in NEU_TAG), "B2: ohne Zähler keine Zahl"
    def _ohne_neu(t: dict) -> dict:
        # Die Geräte-ID ist die einzige Größe, die zwei Anlagen derselben Lage trennt.
        return {**{k: v for k, v in t.items() if k not in NEU_TAG},
                "wp_geraete": [{**g, "investition_id": None} for g in t["wp_geraete"]]}

    assert _ohne_neu(mit) == _ohne_neu(ohne), "Strom, Wärme, JAZ, Gründe und Kasten des Tages bitgleich"


# ═══ Nacharbeit (Master 25.10.): Monat und Jahr · Geräte-Regel ═══════════════
#
# H2 entschieden «den Leser bauen»: Cockpit → Monat und Cockpit → Jahr tragen dieselben sechs Felder wie der Tag,
# aus den Monats-Fakten (`WpFakten.heizstab_kwh`) über `waerme_klima_block.ohne_zusatzheizung_felder`. Geräte-Regel
# für alle anlagenweiten Sichten: die Zahl nur, wenn JEDE Wärmepumpe mit Strom-Beitrag einen Heizstab-Zähler trägt.

from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_GERAETE_OHNE_ZUSATZHEIZUNG  # noqa: E402


def test_layer_geraete_regel():
    sys = systemarbeitszahl(26.0, 6.0)
    az = arbeitszahl_ohne_zusatzheizung(sys, 0.4, nicht_alle_geraete=True)
    assert az.wert is None and az.grund == GRUND_GERAETE_OHNE_ZUSATZHEIZUNG
    assert grund_klasse(GRUND_GERAETE_OHNE_ZUSATZHEIZUNG) == GRUND_KLASSE_AUSSTATTUNG
    assert HANDGRIFF_JE_GRUND[GRUND_GERAETE_OHNE_ZUSATZHEIZUNG]
    # Die Sperre der Hauptzahl geht vor (derselbe Grund wie dort).
    gesperrt = systemarbeitszahl(26.0, 6.0, abgrenzung_verletzt=GRUND_FREMDSTROM)
    assert arbeitszahl_ohne_zusatzheizung(gesperrt, 0.4, nicht_alle_geraete=True).grund == GRUND_FREMDSTROM


def _ohne_neu_monat(m: dict) -> dict:
    return {k: v for k, v in m.items() if k not in NEU_TAG and k != "aktualisiert_um"}


@pytest.mark.asyncio
async def test_monat_mit_und_ohne_zaehler_summen_unveraendert(db):
    a, inv = await _lage(db, MONAT_OHNE, name="P433-3 S2 Monat")
    vorher = (await _monat(db, a.id)).model_dump()
    assert all(vorher[k] is None for k in NEU_TAG), "ohne Zähler keine Zahl (B10)"

    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)
    nachher = (await _monat(db, a.id)).model_dump()

    assert nachher["wp_jaz"] == pytest.approx(2600 / 600), "H-B bleibt die Hauptzahl"
    assert nachher["wp_heizstab_kwh"] == pytest.approx(40.0)
    assert nachher["wp_jaz_ohne_zusatzheizung"] == pytest.approx(2560 / 560)
    assert (nachher["wp_jaz_ohne_zusatzheizung_zaehler_kwh"], nachher["wp_jaz_ohne_zusatzheizung_nenner_kwh"]) == (
        pytest.approx(2560.0), pytest.approx(560.0))
    assert nachher["wp_jaz_ohne_zusatzheizung_hinweis"] == HINWEIS_OHNE_ZUSATZHEIZUNG
    assert _ohne_neu_monat(nachher) == _ohne_neu_monat(vorher), "Strom, Wärme, Ersparnis, CO₂ des Monats bitgleich"


async def _zweite_wp(db, a, daten: dict):
    return await _geraet(db, a, "WP 2", dict(_WP_GESAMT), dict(daten))


@pytest.mark.asyncio
async def test_monat_zwei_wp_nur_eine_mit_zaehler_gibt_den_grund(db):
    a, inv = await _lage(db, {**MONAT_OHNE, FELD: HEIZSTAB_MONAT}, name="P433-3 S2 zwei WP")
    await _zweite_wp(db, a, {"stromverbrauch_kwh": 300.0, "waerme_kwh": 900.0})
    await db.commit()
    m = await _monat(db, a.id)
    assert m.wp_heizstab_kwh == pytest.approx(40.0), "Summe der gemessenen"
    assert m.wp_jaz_ohne_zusatzheizung is None
    assert m.wp_jaz_ohne_zusatzheizung_grund == GRUND_GERAETE_OHNE_ZUSATZHEIZUNG


@pytest.mark.asyncio
async def test_monat_zwei_wp_beide_mit_zaehler_gibt_die_zahl(db):
    a, inv = await _lage(db, {**MONAT_OHNE, FELD: HEIZSTAB_MONAT}, name="P433-3 S2 zwei WP beide")
    await _zweite_wp(db, a, {"stromverbrauch_kwh": 300.0, "waerme_kwh": 900.0, FELD: 10.0})
    await db.commit()
    m = await _monat(db, a.id)
    assert m.wp_heizstab_kwh == pytest.approx(50.0)
    assert m.wp_jaz_ohne_zusatzheizung == pytest.approx((3500 - 50) / (900 - 50))
    assert m.wp_jaz_ohne_zusatzheizung_grund is None


@pytest.mark.asyncio
async def test_jahr_ist_die_summe_der_monate_und_summen_unveraendert(db):
    from backend.services.jahres_aggregat import baue_jahr

    a, inv = await _lage(db, {**MONAT_OHNE, FELD: HEIZSTAB_MONAT}, name="P433-3 S2 Jahr")
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT + 1,
                                  verbrauch_daten={"stromverbrauch_kwh": 400.0, "waerme_kwh": 1500.0, FELD: 20.0}))
    await db.commit()

    kopf = (await baue_jahr(db, a.id, JAHR))["kopf"]
    kopf = kopf.model_dump() if hasattr(kopf, "model_dump") else kopf
    assert kopf["wp_heizstab_kwh"] == pytest.approx(60.0), "Σ der Monate"
    assert kopf["wp_jaz_ohne_zusatzheizung"] == pytest.approx((4100 - 60) / (1000 - 60))
    assert kopf["wp_jaz_ohne_zusatzheizung_grund"] is None


@pytest.mark.asyncio
async def test_jahr_summen_unveraendert(db):
    from backend.services.jahres_aggregat import baue_jahr

    a, inv = await _lage(db, MONAT_OHNE, name="P433-3 S2 Jahr Summen")

    def _kopf(j):
        k = j["kopf"]
        k = k.model_dump() if hasattr(k, "model_dump") else dict(k)
        return k

    vorher = _kopf(await baue_jahr(db, a.id, JAHR))
    assert all(vorher.get(k) is None for k in NEU_TAG)
    await _heizstab_eintragen(db, inv, HEIZSTAB_MONAT)
    nachher = _kopf(await baue_jahr(db, a.id, JAHR))
    assert nachher["wp_jaz_ohne_zusatzheizung"] == pytest.approx(2560 / 560)
    assert _ohne_neu_monat(nachher) == _ohne_neu_monat(vorher), "Jahr: Mengen, JAZ, Ersparnis, CO₂ bitgleich"


@pytest.mark.asyncio
async def test_tag_zwei_wp_nur_eine_mit_zaehler_gibt_den_grund(db):
    a = await _tag_lage(db, heizstab=0.4)
    inv2 = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP 2",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0, parameter=dict(_WP_GESAMT),
    )
    db.add(inv2)
    await db.flush()
    _tageszaehler(db, a, inv2, "stromverbrauch_kwh", 3.0)
    _tageszaehler(db, a, inv2, "waerme_kwh", 9.0)
    tz = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == a.id))).scalars().one()
    tz.komponenten_kwh = {**tz.komponenten_kwh, f"waermepumpe_{inv2.id}": 3.0}
    flag_modified(tz, "komponenten_kwh")
    a.sensor_mapping = dict(a.sensor_mapping)
    flag_modified(a, "sensor_mapping")
    await db.commit()

    t = await _tag(db, a.id)
    assert t.wp_heizstab_kwh == pytest.approx(0.4)
    assert t.wp_jaz_ohne_zusatzheizung is None
    assert t.wp_jaz_ohne_zusatzheizung_grund == GRUND_GERAETE_OHNE_ZUSATZHEIZUNG

    _tageszaehler(db, a, inv2, FELD, 0.1)
    a.sensor_mapping = dict(a.sensor_mapping)
    flag_modified(a, "sensor_mapping")
    await db.commit()
    t2 = await _tag(db, a.id)
    assert t2.wp_heizstab_kwh == pytest.approx(0.5)
    assert t2.wp_jaz_ohne_zusatzheizung == pytest.approx((35 - 0.5) / (9 - 0.5))
