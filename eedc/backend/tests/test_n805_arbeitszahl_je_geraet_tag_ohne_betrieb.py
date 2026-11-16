"""**N-805 (#446): die Gerätezeile des Tages trennt «gemessen 0» von «nicht erfasst» wie die Anlagenebene.**

Melder BMeyendriesch (GitHub #446, v4.3.1): *Cockpit → Tag*, Kasten «Was noch möglich wäre» —
«Arbeitszahl Warmwasser — <Gerät>: kein Stromverbrauch erfasst → Stromzähler zuordnen …», obwohl Strom- und
Wärmezähler fürs Warmwasser zugeordnet sind; der Tag hatte nur noch keine Warmwasserbereitung (0,0 / 0,0).
Die Anlagenebene (``tag.py::_arbeitszahl_je_funktion``, ``null_ist_gemessen=True``) sagte «keine
Warmwasserbereitung in diesem Zeitraum», die Geräteebene (``kennzahlen_aus_mengen``) rief den Layer ohne die
Angabe und landete bei ``GRUND_KEIN_STROM``.

Die Korrektur: ``mengen_aus_tageswerten`` bekommt je Funktion «Strom/Wärme dieses Geräts hat einen Tageswert»
(Schlüssel in ``TagesDetail.werte_je_inv``) und bildet daraus ``null_ist_gemessen_<funktion>`` mit derselben
Regel wie Monat und Jahr anlagenweit (Strom gemessen **und** Wärme gemessen oder Gesamtzähler, N-438/S3, H-3).
Nachtrag (Master, 16.11.2026): dasselbe Fehlbild trug die Geräteebene in Monat, Jahr und Hub —
``mengen_aus_monatszeilen`` bildet die Marken jetzt je Zeile aus ``imd_typ_beitrag`` (ODER über die Zeilen), der
laufende Monat aus den Tagesmengen (``aktueller_monat/waerme.py::_kennzahlen_aus_tagesebene``).

Proben (a)–(f) des Auftrags; Tage über den echten Weg gebaut (``komponenten_kwh`` + ``SensorSnapshot``-Randstände
+ ``sensor_mapping``), dieselbe Bauform wie die Schwester ``test_wk16j_tag_deckung.py``. Weitere Schwestern:
``test_n348_tag_arbeitszahl_je_funktion.py`` (der Anlagen-Grund am Tag), ``test_n479_zeitraum_grund_monat_jahr.py``
(Monat/Jahr anlagenweit), ``test_e4f_h3_kein_heizbetrieb_vor_waerme_nicht_je_funktion.py`` (H-3).
"""

from __future__ import annotations

from datetime import date, datetime

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_KEIN_HEIZBETRIEB,
    GRUND_KEIN_STROM,
    GRUND_KEINE_WARMWASSERBEREITUNG,
    HANDGRIFF_JE_GRUND,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.waermepumpe_kennzahlen_je_geraet import (
    GeraetMengen,
    kennzahlen_aus_mengen,
    mengen_aus_monatszeilen,
    mengen_aus_tageswerten,
)
from backend.tests import factories

#: Der geprüfte Tag — fest, nie aus der Uhr (N-167).
TAG = date(2026, 11, 16)

_F5 = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "getrennte_strommessung": True}


async def _anlage_mit_tag(db, geraete: list[tuple[str, dict, dict]]):
    """Eine Anlage mit einem aggregierten Tag (Bauform ``test_wk16j_tag_deckung.py::_anlage_mit_tag``).

    ``felder`` = Tageszuwachs je Registry-Feld; ``stromverbrauch_kwh`` geht in ``komponenten_kwh``, jedes andere Feld
    wird zugeordnet und bekommt ein Randstandspaar — ein Zuwachs **0** ist damit ein gemessener Nullwert.
    """
    anlage = await factories.anlage(db, anlagenname="N-805")
    mapping: dict[str, dict] = {}
    invs: list[Investition] = []
    for bezeichnung, parameter, felder in geraete:
        inv = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=bezeichnung,
            anschaffungsdatum=date(2024, 1, 1), parameter=parameter,
        )
        db.add(inv)
        await db.flush()
        invs.append(inv)
        mapping[str(inv.id)] = {"felder": {
            feld: {"strategie": "sensor", "sensor_id": f"sensor.{inv.id}_{feld}"}
            for feld in felder if feld != "stromverbrauch_kwh"
        }}
    anlage.sensor_mapping = {"investitionen": mapping}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=TAG,
        komponenten_kwh={
            f"waermepumpe_{inv.id}": felder["stromverbrauch_kwh"]
            for inv, (_, _, felder) in zip(invs, geraete)
            if felder.get("stromverbrauch_kwh")
        },
    ))
    for inv, (_, _, felder) in zip(invs, geraete):
        for feld, zuwachs in felder.items():
            if feld == "stromverbrauch_kwh":
                continue
            for versatz, wert in ((0, 100.0), (1, 100.0 + zuwachs)):
                db.add(SensorSnapshot(
                    anlage_id=anlage.id, sensor_key=f"inv:{inv.id}:{feld}",
                    zeitpunkt=datetime.combine(date.fromordinal(TAG.toordinal() + versatz), datetime.min.time()),
                    wert_kwh=wert, quelle="ha_statistics",
                ))
    await db.commit()
    return anlage, invs


async def _tag(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_tag_detail
    return await get_tag_detail(anlage_id=anlage_id, datum=TAG, db=db)


def _geraet(t, name):
    return next(g for g in t.wp_geraete if g.name == name)


def _kasten_gruende(t) -> list[str]:
    return [z.grund for z in t.wp_moeglich]


#: Der Fall des Melders: Heizen läuft, Warmwasser gemessen 0 / 0 (beide Zähler zugeordnet).
_WW_RUHT = ("Melder-WP", _F5, {
    "stromverbrauch_kwh": 2.5, "heizenergie_kwh": 10.0, "warmwasser_kwh": 0.0,
    "strom_heizen_kwh": 2.5, "strom_warmwasser_kwh": 0.0,
})
#: Spiegelbild «Heizen»: Sommertag, Heizen gemessen 0 / 0, Warmwasser läuft.
_HEIZEN_RUHT = ("Sommer-WP", _F5, {
    "stromverbrauch_kwh": 1.5, "heizenergie_kwh": 0.0, "warmwasser_kwh": 4.5,
    "strom_heizen_kwh": 0.0, "strom_warmwasser_kwh": 1.5,
})
#: Beide Funktionen laufen: 10,0 ÷ 2,5 = 4,0 · 4,5 ÷ 1,5 = 3,0.
_BETRIEB = ("Betriebs-WP", _F5, {
    "stromverbrauch_kwh": 4.0, "heizenergie_kwh": 10.0, "warmwasser_kwh": 4.5,
    "strom_heizen_kwh": 2.5, "strom_warmwasser_kwh": 1.5,
})
#: Kein Stromzähler fürs Warmwasser zugeordnet (Wärmezähler schon, Tag 0).
_OHNE_WW_STROM = ("WP ohne WW-Strom", _F5, {
    "stromverbrauch_kwh": 2.5, "heizenergie_kwh": 10.0, "warmwasser_kwh": 0.0,
    "strom_heizen_kwh": 2.5,
})


# ── (a) zugeordnete Zähler, Tag 0/0 ⇒ Zeitraum-Grund, kein Handgriff ────────────────────────────────────────────


async def test_a_warmwasser_ruht_geraet_sagt_wie_die_anlage(db):
    anlage, _ = await _anlage_mit_tag(db, [_WW_RUHT])
    t = await _tag(db, anlage.id)

    assert t.wp_jaz_warmwasser_grund == GRUND_KEINE_WARMWASSERBEREITUNG
    g = _geraet(t, "Melder-WP")
    assert g.jaz_warmwasser is None
    assert g.jaz_warmwasser_grund == GRUND_KEINE_WARMWASSERBEREITUNG, "vor N-805: «kein Stromverbrauch erfasst»"
    assert round(g.jaz_heizen, 3) == 4.0
    assert t.wp_moeglich == [], "kein Eintrag mit Handgriff «Datenquellen» an einem Tag ohne Warmwasserbereitung"


# ── (b) kein Stromzähler für die Funktion ⇒ weiter «kein Stromverbrauch erfasst» mit Handgriff ──────────────────


async def test_b_ohne_stromzaehler_der_funktion_bleibt_der_handgriff(db):
    anlage, _ = await _anlage_mit_tag(db, [_OHNE_WW_STROM])
    t = await _tag(db, anlage.id)

    g = _geraet(t, "WP ohne WW-Strom")
    assert g.jaz_warmwasser is None
    assert g.jaz_warmwasser_grund == GRUND_KEIN_STROM
    zeilen = [z for z in t.wp_moeglich if GRUND_KEIN_STROM in z.grund]
    assert zeilen, _kasten_gruende(t)
    assert all(z.handgriff == HANDGRIFF_JE_GRUND[GRUND_KEIN_STROM] and z.link for z in zeilen)


# ── (c) Tag mit Betrieb ⇒ Arbeitszahl wie bisher ────────────────────────────────────────────────────────────────


async def test_c_tag_mit_betrieb_rechnet_wie_bisher(db):
    anlage, _ = await _anlage_mit_tag(db, [_BETRIEB])
    t = await _tag(db, anlage.id)

    g = _geraet(t, "Betriebs-WP")
    assert round(g.jaz_heizen, 3) == 4.0 and g.jaz_heizen_grund is None
    assert round(g.jaz_warmwasser, 3) == 3.0 and g.jaz_warmwasser_grund is None
    assert round(t.wp_jaz_heizen, 3) == 4.0 and round(t.wp_jaz_warmwasser, 3) == 3.0
    assert t.wp_moeglich == []


# ── (d) dasselbe für «Heizen» ───────────────────────────────────────────────────────────────────────────────────


async def test_d_heizen_ruht_geraet_sagt_kein_heizbetrieb(db):
    anlage, _ = await _anlage_mit_tag(db, [_HEIZEN_RUHT])
    t = await _tag(db, anlage.id)

    assert t.wp_jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB
    g = _geraet(t, "Sommer-WP")
    assert g.jaz_heizen is None
    assert g.jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB, "vor N-805: «kein Stromverbrauch erfasst»"
    assert round(g.jaz_warmwasser, 3) == 3.0
    assert t.wp_moeglich == []


async def test_d_gemeinsamer_waermezaehler_heizen_ruht(db):
    """H-3 je Gerät: Gesamt-Wärmezähler, Heizstrom gemessen 0 ⇒ «kein Heizbetrieb» (wie Monat/Jahr anlagenweit)."""
    gesamt = ("Gesamtzähler-WP", _F5, {
        "stromverbrauch_kwh": 1.5, "waerme_kwh": 4.5,
        "strom_heizen_kwh": 0.0, "strom_warmwasser_kwh": 1.5,
    })
    anlage, _ = await _anlage_mit_tag(db, [gesamt])
    t = await _tag(db, anlage.id)

    g = _geraet(t, "Gesamtzähler-WP")
    assert g.jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB == t.wp_jaz_heizen_grund
    assert GRUND_KEIN_STROM not in " ".join(_kasten_gruende(t))


# ── (e) zwei Wärmepumpen, eine mit, eine ohne Betrieb ───────────────────────────────────────────────────────────


async def test_e_zwei_waermepumpen_eine_ruht(db):
    anlage, _ = await _anlage_mit_tag(db, [_WW_RUHT, _BETRIEB])
    t = await _tag(db, anlage.id)

    ruht, laeuft = _geraet(t, "Melder-WP"), _geraet(t, "Betriebs-WP")
    assert ruht.jaz_warmwasser_grund == GRUND_KEINE_WARMWASSERBEREITUNG
    assert round(laeuft.jaz_warmwasser, 3) == 3.0 and laeuft.jaz_warmwasser_grund is None
    # Anlage: (0 + 4,5) ÷ (0 + 1,5) = 3,0 — die ruhende WP verschiebt die Zahl nicht.
    assert round(t.wp_jaz_warmwasser, 3) == 3.0
    assert not any("Melder-WP" in gr for gr in _kasten_gruende(t)), _kasten_gruende(t)


async def test_e_zwei_waermepumpen_eine_ohne_stromzaehler(db):
    """Gegenprobe zu (e): fehlt einem der beiden Geräte der Warmwasser-Stromzähler, nennt der Kasten genau dieses."""
    anlage, _ = await _anlage_mit_tag(db, [_OHNE_WW_STROM, _BETRIEB])
    t = await _tag(db, anlage.id)

    assert _geraet(t, "WP ohne WW-Strom").jaz_warmwasser_grund == GRUND_KEIN_STROM
    zeile = next(z for z in t.wp_moeglich if z.grund == f"WP ohne WW-Strom: {GRUND_KEIN_STROM}")
    assert zeile.handgriff == HANDGRIFF_JE_GRUND[GRUND_KEIN_STROM]


# ── (f) Monat · Jahr · Hub: dieselbe Regel aus den Monatszeilen (Nachtrag Master 16.11.2026) ──────────────────
#
# Die Annahme «nur der Tag» war falsch (gemessen r28, Cockpit → Monat Juli 2026: Nibe und Vaillant «kein
# Stromverbrauch erfasst» mit Handgriff). ``mengen_aus_monatszeilen`` bildet die Marken je Zeile aus der einen Lesetür
# ``imd_typ_beitrag`` (Feld steht in der Zeile, auch mit 0) und über die Zeilen ODER — wie
# ``waermepumpe_jahreskennzahlen.py`` anlagenweit (N-479).


class _Inv:
    typ = "waermepumpe"
    id = 7
    bezeichnung = "WP"
    parameter = _F5

    @staticmethod
    def ist_aktiv_im_monat(jahr, monat):
        return True


def _zeile(monat, **felder):
    from types import SimpleNamespace
    return SimpleNamespace(jahr=2026, monat=monat, source_provenance={}, verbrauch_daten=felder)


_JULI = dict(strom_heizen_kwh=0.0, heizenergie_kwh=0.0, strom_warmwasser_kwh=24.7, warmwasser_kwh=89.4)
_JANUAR = dict(strom_heizen_kwh=171.0, heizenergie_kwh=704.7, strom_warmwasser_kwh=35.4, warmwasser_kwh=86.9)


def _monat(*zeilen):
    m, _ = mengen_aus_monatszeilen(_Inv(), list(zeilen))
    return m, kennzahlen_aus_mengen(m)


def test_f_monat_ohne_heizbetrieb():
    m, k = _monat(_zeile(7, **_JULI))
    assert m.null_ist_gemessen_heizen is True
    assert k.je_funktion.heizen.wert is None
    assert k.je_funktion.heizen.grund == GRUND_KEIN_HEIZBETRIEB, "vor N-805: «kein Stromverbrauch erfasst»"
    assert round(k.je_funktion.warmwasser.wert, 4) == round(89.4 / 24.7, 4)


def test_f_monat_ohne_warmwasserbereitung():
    _, k = _monat(_zeile(4, strom_heizen_kwh=63.0, heizenergie_kwh=336.0, strom_warmwasser_kwh=0.0,
                         warmwasser_kwh=0.0))
    assert k.je_funktion.warmwasser.grund == GRUND_KEINE_WARMWASSERBEREITUNG
    assert round(k.je_funktion.heizen.wert, 4) == round(336.0 / 63.0, 4)


def test_f_monat_ohne_stromfeld_der_funktion_behaelt_den_grund():
    """Zeile mit getrennter Messung, aber ohne Feld «Strom Warmwasser» ⇒ weiter «kein Stromverbrauch erfasst»."""
    m, k = _monat(_zeile(4, strom_heizen_kwh=63.0, heizenergie_kwh=336.0, warmwasser_kwh=0.0))
    assert m.null_ist_gemessen_warmwasser is False
    assert k.je_funktion.warmwasser.grund == GRUND_KEIN_STROM


def test_f_monat_strom_null_ohne_waermefeld_behaelt_den_grund():
    """Strom Heizen gemessen 0, aber kein Heizwärme-Feld und kein Gesamtzähler ⇒ keine Marke (Regel: beide Seiten)."""
    m, k = _monat(_zeile(7, strom_heizen_kwh=0.0, strom_warmwasser_kwh=24.7, warmwasser_kwh=89.4))
    assert m.null_ist_gemessen_heizen is False
    assert k.je_funktion.heizen.grund == GRUND_KEIN_STROM


def test_f_gesamtzaehler_zaehlt_als_waerme_gemessen():
    """H-3 im Monat: gemeinsamer Wärmemengenzähler, Strom Heizen 0 ⇒ «kein Heizbetrieb» (wie die Vaillant der r28)."""
    m, k = _monat(_zeile(7, strom_heizen_kwh=0.0, strom_warmwasser_kwh=28.3, waerme_kwh=109.1))
    assert m.null_ist_gemessen_heizen is True
    assert k.je_funktion.heizen.grund == GRUND_KEIN_HEIZBETRIEB


def test_f_jahr_oder_ueber_die_zeilen():
    """Ganzer Zeitraum ohne Heizbetrieb ⇒ Zeitraum-Grund; ein Monat mit Betrieb ⇒ die Zahl wie bisher."""
    _, k = _monat(_zeile(6, **_JULI), _zeile(7, **_JULI), _zeile(8, **_JULI))
    assert k.je_funktion.heizen.grund == GRUND_KEIN_HEIZBETRIEB
    _, k = _monat(_zeile(1, **_JANUAR), _zeile(7, **_JULI))
    assert round(k.je_funktion.heizen.wert, 4) == round(704.7 / 171.0, 4) and k.je_funktion.heizen.grund is None


def test_f_keine_zahl_aendert_sich():
    """Die Marken ändern nur einen Grund: Mit und ohne Marke sind alle Werte gleich (Gesamt, je Funktion, Kühlen)."""
    import dataclasses

    zeilen_saetze = [
        [_zeile(7, **_JULI)], [_zeile(1, **_JANUAR)], [_zeile(1, **_JANUAR), _zeile(7, **_JULI)],
        [_zeile(4, strom_heizen_kwh=63.0, heizenergie_kwh=336.0, strom_warmwasser_kwh=0.0, warmwasser_kwh=0.0)],
        [_zeile(7, strom_heizen_kwh=0.0, strom_warmwasser_kwh=28.3, waerme_kwh=109.1)],
        [_zeile(7, strom_heizen_kwh=2.0, heizenergie_kwh=0.0, strom_warmwasser_kwh=0.0, warmwasser_kwh=3.0)],
    ]
    for zeilen in zeilen_saetze:
        m, k = _monat(*zeilen)
        ohne = kennzahlen_aus_mengen(dataclasses.replace(
            m, null_ist_gemessen_heizen=False, null_ist_gemessen_warmwasser=False))
        for a, b in ((k.gesamt, ohne.gesamt), (k.je_funktion.heizen, ohne.je_funktion.heizen),
                     (k.je_funktion.warmwasser, ohne.je_funktion.warmwasser), (k.kuehlen, ohne.kuehlen)):
            assert (a.wert, a.zaehler_kwh, a.nenner_kwh) == (b.wert, b.zaehler_kwh, b.nenner_kwh), zeilen


async def _anlage_mit_monaten(db, geraete: list[tuple[str, dict, dict[int, dict]]]):
    anlage = await factories.anlage(db, anlagenname="N-805 Monat")
    invs = []
    for bezeichnung, parameter, monate in geraete:
        inv = await factories.investition(db, anlage.id, "waermepumpe", bezeichnung=bezeichnung,
                                          anschaffungsdatum=date(2024, 1, 1), parameter=parameter)
        invs.append(inv)
        for monat, felder in monate.items():
            await factories.imd(db, investition_id=inv.id, jahr=2025, monat=monat, verbrauch_daten=felder)
    await db.commit()
    return anlage, invs


async def test_f_cockpit_monat_zwei_geraete(db):
    """Cockpit → Monat Juli: Gerät A ruht beim Heizen (Zeitraum-Grund, kein Kasten), Gerät B hat kein Feld
    «Strom Warmwasser» (Grund und Handgriff bleiben)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage, _ = await _anlage_mit_monaten(db, [
        ("Ruhende WP", _F5, {7: _JULI}),
        ("WP ohne WW-Strom", _F5, {7: dict(strom_heizen_kwh=0.0, heizenergie_kwh=0.0, warmwasser_kwh=50.0)}),
    ])
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=7, db=db)
    g = {z.name: z for z in r.wp_geraete}
    assert g["Ruhende WP"].jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB
    assert g["WP ohne WW-Strom"].jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB
    assert g["WP ohne WW-Strom"].jaz_warmwasser_grund == GRUND_KEIN_STROM
    gruende = [z.grund for z in r.wp_moeglich]
    assert not any("Ruhende WP" in gr for gr in gruende), gruende
    assert not any(GRUND_KEIN_STROM in gr and "Heizen" in z.groesse for z in r.wp_moeglich for gr in [z.grund])
    zeile = next(z for z in r.wp_moeglich if GRUND_KEIN_STROM in z.grund)
    assert zeile.handgriff == HANDGRIFF_JE_GRUND[GRUND_KEIN_STROM]


async def test_f_cockpit_jahr_und_hub_ganzer_zeitraum_ohne_heizbetrieb(db):
    """Ein Gerät, das im ganzen Jahr bzw. in seiner ganzen Laufzeit nicht heizt (Brauchwasser-Betrieb über die
    Heizungs-WP): Cockpit → Jahr und der Komponenten-Hub nennen den Zeitraum-Grund, die Warmwasser-Zahl bleibt."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard

    anlage, _ = await _anlage_mit_monaten(db, [
        ("Sommer-WP", _F5, {6: _JULI, 7: _JULI, 8: _JULI}),
        ("Zweite WP", _F5, {6: _JANUAR, 7: _JANUAR, 8: _JANUAR}),
    ])
    jahr = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=db)
    g = {z.name: z for z in jahr.wp_geraete}
    assert g["Sommer-WP"].jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB
    assert round(g["Sommer-WP"].jaz_warmwasser, 2) == round(89.4 / 24.7, 2)
    assert round(g["Zweite WP"].jaz_heizen, 2) == round(704.7 / 171.0, 2)
    assert not any("Sommer-WP" in z.grund for z in jahr.wp_moeglich)

    hub = await get_waermepumpe_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    z = {w.investition.bezeichnung: w.zusammenfassung for w in hub}
    assert z["Sommer-WP"]["jaz_heizen_grund"] == GRUND_KEIN_HEIZBETRIEB
    assert z["Zweite WP"]["jaz_heizen_grund"] is None


# ── laufender Monat aus Tagesmengen ─────────────────────────────────────────────────────────────────────────────


def test_f_laufender_monat_aus_tagen():
    """``_kennzahlen_aus_tagesebene``: ein Gerät ohne Monatszeile bekommt die Marke aus den Tagesmengen
    («an mindestens einem Tag gemessen») — Heizen 0/0 ⇒ Zeitraum-Grund; ohne Strom-Heizen-Feld ⇒ Grund bleibt."""
    from types import SimpleNamespace

    from backend.api.routes.aktueller_monat.waerme import _kennzahlen_aus_tagesebene

    leer = kennzahlen_aus_mengen(GeraetMengen(inv_id=7, name="WP"))
    basis = dict(strom_kwh=1.5, waerme_kwh=0.0, heizung_kwh=0.0, warmwasser_kwh=4.5, strom_heizen_kwh=0.0,
                 strom_warmwasser_kwh=1.5, kaelte_kwh=0.0, modus_strom_kuehlen_kwh=0.0, funktionsfremd_abzug_kwh=0.0)
    alle = frozenset({"strom_kwh", "heizung_kwh", "warmwasser_kwh", "strom_heizen_kwh", "strom_warmwasser_kwh"})
    for gemessen, soll in ((alle, GRUND_KEIN_HEIZBETRIEB), (alle - {"strom_heizen_kwh"}, GRUND_KEIN_STROM)):
        tage = {"7": SimpleNamespace(gemessen=gemessen, **basis)}
        (k,) = _kennzahlen_aus_tagesebene([leer], tage, [_Inv()])
        assert k.je_funktion.heizen.grund == soll
        assert round(k.je_funktion.warmwasser.wert, 3) == 3.0


def test_marke_nur_mit_strom_und_waerme_der_funktion():
    """Die Regel je Funktion: Strom gemessen UND (Wärme gemessen ODER Gesamtzähler); ohne Kennzeichen keine Wirkung."""
    def _m(**kw):
        basis = dict(strom_kwh=2.5, waerme_kwh=10.0, heizung_kwh=10.0, warmwasser_kwh=0.0, strom_heizen_kwh=2.5,
                     strom_warmwasser_kwh=0.0, kaelte_kwh=0.0, modus_strom_kuehlen_kwh=0.0,
                     funktionsfremd_abzug_kwh=0.0, waerme_ist_gesamt=False)
        return mengen_aus_tageswerten(_Inv(), **{**basis, **kw})

    assert _m(strom_warmwasser_gemessen=True, warmwasser_gemessen=True).null_ist_gemessen_warmwasser is True
    assert _m(strom_warmwasser_gemessen=True).null_ist_gemessen_warmwasser is False, "Wärme fehlt"
    assert _m(warmwasser_gemessen=True).null_ist_gemessen_warmwasser is False, "Strom fehlt"
    assert _m(strom_warmwasser_gemessen=True, waerme_ist_gesamt=True).null_ist_gemessen_warmwasser is True, "H-3"
    k = kennzahlen_aus_mengen(_m(warmwasser_gemessen=True))
    assert k.je_funktion.warmwasser.grund == GRUND_KEIN_STROM
