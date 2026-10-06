"""N-587 — im Monat ohne Abschluss gewinnen die Einzelwerte, der Anlagen-PV-Zähler füllt nur die Lücken.

Gemessen am 03.10.2026 über die echte Route (HA-Statistik nachgestellt wie in
``test_bkw_pv_achse_laufender_monat.py``): zwei Strings (6 + 4 kWp) mit 550 + 380 kWh
und ein Anlagen-PV-Zähler mit 1000 kWh. Der Monat ohne Abschluss nannte **1000**
(der Anlagenzähler als Direktwert, ``direct_fields`` sperrte die Strings), derselbe
Monat nach dem Abschluss **930** — die Zahl sprang beim Monatsabschluss.

**Der Anlagen-PV-Zähler umfasst ALLE PV-Quellen** — PV-Module UND Balkonkraftwerke
(Entscheid Gernot 03.10.2026, Variante B; so lesen ihn Tagesregel, Datenquellen-Prüfung
und Handbuch §7.6). Grundgesamtheit wie am Tag (``erwartete_erzeuger_ids``): aktive Module
+ BKW über ``erzeuger_traeger``. Alle mit eigenem Wert ⇒ Σ Einzelwerte; fehlt einer ⇒
Σ gemessene + max(0, Zähler − Σ gemessene). Das BKW kommt NICHT zusätzlich obendrauf;
``bkw_erzeugung_kwh`` bleibt sein eigener Wert.

Seit **N-611** liest der abgeschlossene Monat (Monats-Fakten, Schreibweg N-533) den Zähler
genauso: der eigene BKW-Wert mindert ihn, bevor der Rest die Modul-Lücken füllt. Die zwei
Fälle „Zähler füllt eine Lücke + BKW" standen bis dahin als ``xfail(strict=True)`` hier
(1045 statt 1000) — sie sind jetzt gewöhnliche Fälle der Symmetrie-Probe.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

ANLAGENZAEHLER = 1000.0
JETZT = datetime(2026, 10, 15, 12, 0)


class _FesteUhr(datetime):
    """``datetime`` mit stehengebliebener ``now()`` — wie in ``test_wk16i_laufender_monat_funktionen.py``.

    ``get_aktueller_monat`` entscheidet an ``datetime.now()``, ob der Monat läuft; eine Probe, die dafür die echte
    Uhr liest, wettet auf den Tag ihres Laufs (N-167). Als Subklasse bleibt jeder andere Gebrauch unverändert.
    """

    @classmethod
    def now(cls, tz=None):  # noqa: D102 — Verhalten steht im Klassen-Docstring
        return JETZT


async def _seed(db, *, mit_bkw: bool = False):
    anlage = Anlage(anlagenname="N-587", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    s1 = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0)
    s2 = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=4000.0)
    db.add_all([s1, s2])
    bkw = None
    if mit_bkw:
        bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                          anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=800.0)
        db.add(bkw)
    await db.commit()
    return anlage.id, s1.id, s2.id, (bkw.id if bkw else None)


def _quellen_still(am, monkeypatch, ha_werte: dict):
    async def _leer(*a, **k):
        return {}

    async def _leer_set(*a, **k):
        return set()

    async def _ha(anlage, j, m):
        return dict(ha_werte)

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)
    monkeypatch.setattr(am, "_ha_heimlade_felder_mit_daten", _leer_set)


def _ha_werte(am, *, s1, s2, bkw, strings: dict) -> dict:
    info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, abdeckung_von=None)
    werte = {
        "pv_erzeugung_kwh": (ANLAGENZAEHLER, info),
        "einspeisung_kwh": (400.0, info),
        "netzbezug_kwh": (200.0, info),
    }
    for inv_id, kwh in ((s1, strings.get("s1")), (s2, strings.get("s2"))):
        if kwh is not None:
            werte[f"inv_{inv_id}_pv_erzeugung_kwh"] = (kwh, info)
    if bkw is not None:
        werte[f"inv_{bkw}_pv_erzeugung_kwh"] = (45.0, info)
    return werte


async def _monat_ohne_abschluss(db, monkeypatch, *, strings: dict, mit_bkw=False, laufend=True):
    import backend.api.routes.aktueller_monat as am
    monkeypatch.setattr(am, "datetime", _FesteUhr)
    jahr, monat = (JETZT.year, JETZT.month) if laufend else (2025, 5)
    aid, s1, s2, bkw = await _seed(db, mit_bkw=mit_bkw)
    _quellen_still(am, monkeypatch, _ha_werte(am, s1=s1, s2=s2, bkw=bkw, strings=strings))
    return await am.get_aktueller_monat(anlage_id=aid, jahr=jahr, monat=monat, db=db)


@pytest.mark.parametrize("laufend", [True, False], ids=["laufend", "vergangen-ohne-abschluss"])
async def test_a_alle_strings_gemessen_der_anlagenzaehler_ist_wirkungslos(db, monkeypatch, laufend):
    """(a) 550 + 380 gemessen, Anlagenzähler 1000 ⇒ 930 (bis 03.10.2026: 1000)."""
    res = await _monat_ohne_abschluss(db, monkeypatch, strings={"s1": 550.0, "s2": 380.0}, laufend=laufend)
    assert res.pv_erzeugung_kwh == 930.0
    # Die Bilanz rechnet mit derselben Zahl: EV = PV − Einspeisung.
    assert res.eigenverbrauch_kwh == 530.0


async def test_a_auch_wenn_der_anlagenzaehler_ueber_mqtt_kommt(db, monkeypatch):
    """(a) über MQTT-Inbound (`pv_gesamt_kwh` → `pv_erzeugung_kwh`, ab Monatsbeginn) statt HA-Statistik ⇒ 930."""
    import backend.api.routes.aktueller_monat as am
    monkeypatch.setattr(am, "datetime", _FesteUhr)
    aid, s1, s2, _bkw = await _seed(db)
    info = am.DatenquelleInfo(quelle="mqtt_inbound", konfidenz=91, abdeckung_von=None)
    mqtt = {
        "pv_erzeugung_kwh": (ANLAGENZAEHLER, info),
        "einspeisung_kwh": (400.0, info),
        "netzbezug_kwh": (200.0, info),
        f"inv_{s1}_pv_erzeugung_kwh": (550.0, info),
        f"inv_{s2}_pv_erzeugung_kwh": (380.0, info),
    }

    async def _mqtt(db_, anlage, investitionen, jahr, monat):
        return dict(mqtt)

    _quellen_still(am, monkeypatch, {})
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _mqtt)
    res = await am.get_aktueller_monat(anlage_id=aid, jahr=JETZT.year, monat=JETZT.month, db=db)
    assert res.pv_erzeugung_kwh == 930.0


async def test_b_ein_string_ohne_wert_bekommt_den_rest(db, monkeypatch):
    """(b) Süd 550 gemessen, West ohne Wert ⇒ 550 + Rest (1000 − 550) = 1000."""
    res = await _monat_ohne_abschluss(db, monkeypatch, strings={"s1": 550.0})
    assert res.pv_erzeugung_kwh == 1000.0


async def test_b_rest_wird_bei_null_geklemmt(db, monkeypatch):
    """(b) Süd 1100 gemessen (> Anlagenzähler), West ohne Wert ⇒ 1100, nicht 1000.

    Diskriminiert gegen beide Fehlformen: den Direktwert (1000) und einen ungeklemmten
    Rest (1100 − 100 = 1000).
    """
    res = await _monat_ohne_abschluss(db, monkeypatch, strings={"s1": 1100.0})
    assert res.pv_erzeugung_kwh == 1100.0


async def test_c_ohne_jeden_stringwert_traegt_der_anlagenzaehler(db, monkeypatch):
    """(c) kein String-Wert ⇒ der Anlagenzähler allein (1000)."""
    res = await _monat_ohne_abschluss(db, monkeypatch, strings={})
    assert res.pv_erzeugung_kwh == ANLAGENZAEHLER


@pytest.mark.parametrize(
    "strings, mit_bkw, erwartet",
    [
        ({"s1": 550.0, "s2": 380.0}, True, 975.0),
        ({"s1": 550.0}, True, 1000.0),
        ({}, True, 1000.0),
    ],
    ids=["alle-strings+bkw", "ein-string-ohne-wert+bkw", "keine-strings+bkw"],
)
async def test_das_balkonkraftwerk_gehoert_zur_grundgesamtheit_des_zaehlers(db, monkeypatch, strings, mit_bkw, erwartet):
    """Variante B: das BKW ist eine PV-Quelle wie ein String. Alle gemessen ⇒ 550 + 380 + 45 = 975; fehlt ein
    String ⇒ der Zähler trägt (1000), das BKW kommt NICHT obendrauf. Seine eigene Zeile bleibt 45."""
    res = await _monat_ohne_abschluss(db, monkeypatch, strings=strings, mit_bkw=mit_bkw)
    assert res.pv_erzeugung_kwh == erwartet
    assert res.bkw_erzeugung_kwh == 45.0


async def _nach_dem_abschluss(db, monkeypatch, *, strings: dict, mit_bkw: bool, ha_werte_fn=None):
    """Derselbe Monat abgeschlossen: Stringwerte gespeichert, der Anlagenzähler als Anlagenwert in der Zählerzeile —
    so speichert ihn der HA-Sammelimport seit HA-Bauform E4b (vorher `_verteile_anlagen_pv`, N-533: auf die Lücken
    verteilt) und „Aus HA laden" seit N-622; die Monats-Fakten lösen ihn auf (P7)."""
    import backend.api.routes.aktueller_monat as am

    jahr, monat = 2025, 5
    aid, s1, s2, bkw = await _seed(db, mit_bkw=mit_bkw)
    db.add(Monatsdaten(anlage_id=aid, jahr=jahr, monat=monat, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=ANLAGENZAEHLER))
    for inv_id, kwh in ((s1, strings.get("s1")), (s2, strings.get("s2")), (bkw, 45.0 if mit_bkw else None)):
        if kwh is not None:
            db.add(InvestitionMonatsdaten(investition_id=inv_id, jahr=jahr, monat=monat,
                                          verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    await db.commit()
    _quellen_still(am, monkeypatch, ha_werte_fn(am, s1, s2, bkw) if ha_werte_fn else {})
    return await am.get_aktueller_monat(anlage_id=aid, jahr=jahr, monat=monat, db=db)


_FAELLE = [
    pytest.param({"s1": 550.0, "s2": 380.0}, False, id="alle"),
    pytest.param({"s1": 550.0}, False, id="einer"),
    pytest.param({}, False, id="keiner"),
    pytest.param({"s1": 550.0, "s2": 380.0}, True, id="alle+bkw"),
    pytest.param({"s1": 550.0}, True, id="einer+bkw"),
    pytest.param({}, True, id="keiner+bkw"),
]


@pytest.mark.parametrize("strings, mit_bkw", _FAELLE)
async def test_d_der_monat_rechnet_wie_der_tag(db, monkeypatch, strings, mit_bkw):
    """(d) Symmetrie gegen den TAG: dieselbe Grundgesamtheit (``erwartete_erzeuger_ids``) und dieselbe Wahl
    (``waehle_pv_quelle``, ein Pseudo-Slot wie im Tagespfad) — alle Erzeuger mit Wert ⇒ Σ Einzelwerte, sonst
    der Zähler. (Gilt, solange Σ gemessene ≤ Zähler; darüber klemmt der Monat, siehe ``test_b_rest_wird_bei_null_geklemmt``.)"""
    from backend.core.berechnungen.pv_tages_praezedenz import (
        QUELLE_EINZEL, erwartete_erzeuger_ids, waehle_pv_quelle,
    )
    from backend.models import Investition
    from sqlalchemy import select

    res = await _monat_ohne_abschluss(db, monkeypatch, strings=strings, mit_bkw=mit_bkw, laufend=False)
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == res.anlage_id))).scalars().all()
    erwartet_ids = erwartete_erzeuger_ids(invs, date(2025, 5, 15))
    einzel = {}
    for inv in invs:
        if inv.typ == "pv-module":
            wert = strings.get("s1" if inv.bezeichnung == "Süd" else "s2")
        elif inv.typ == "balkonkraftwerk":
            wert = 45.0
        else:
            wert = None
        if wert is not None:
            einzel[str(inv.id)] = wert
    wahl = waehle_pv_quelle(
        erwartete_ids=erwartet_ids, gedeckte_ids_je_slot={0: set(einzel)}, aggregat_je_slot={0: ANLAGENZAEHLER},
    )
    tag = sum(einzel.values()) if wahl == QUELLE_EINZEL else ANLAGENZAEHLER
    assert res.pv_erzeugung_kwh == tag


@pytest.mark.parametrize("strings, mit_bkw", _FAELLE)
async def test_d_der_monat_nennt_vor_und_nach_dem_abschluss_dieselbe_pv(db, monkeypatch, strings, mit_bkw):
    """(d) Symmetrie gegen den abgeschlossenen Monat (Monats-Fakten/P7, Schreibpfad N-533) — alle sechs
    Fälle, seit N-611 auch die zwei, in denen der Zähler eine Lücke füllt und ein BKW einen eigenen Wert hat
    (vorher 1045 gegen 1000)."""
    vorher = await _monat_ohne_abschluss(db, monkeypatch, strings=strings, mit_bkw=mit_bkw, laufend=False)
    nachher = await _nach_dem_abschluss(db, monkeypatch, strings=strings, mit_bkw=mit_bkw)
    assert vorher.pv_erzeugung_kwh == nachher.pv_erzeugung_kwh
    assert vorher.eigenverbrauch_kwh == nachher.eigenverbrauch_kwh


async def test_der_gespeicherte_wert_bleibt_vor_der_ha_statistik(db, monkeypatch):
    """Die Quellen-Präzedenz bleibt: im abgeschlossenen Monat gilt der gespeicherte (P7-aufgelöste) Wert,
    auch wenn die HA-Statistik Anlagenzähler UND abweichende Strings liefert."""
    def _ha_anders(am, s1, s2, bkw):
        werte = _ha_werte(am, s1=s1, s2=s2, bkw=bkw, strings={"s1": 600.0, "s2": 450.0})
        return werte

    res = await _nach_dem_abschluss(
        db, monkeypatch, strings={"s1": 550.0, "s2": 380.0}, mit_bkw=False, ha_werte_fn=_ha_anders,
    )
    assert res.pv_erzeugung_kwh == 930.0


async def test_ein_bkw_mit_modul_kindern_tritt_an_sie_ab(db, monkeypatch):
    """Grundgesamtheit wie am Tag über ``erzeuger_traeger`` (N-266): hängen die Strings an einem BKW, ist das BKW
    selbst keine eigene PV-Quelle mehr — 550 + 380 = 930, nicht 930 + 930 (BKW-Zähler 930 = seine Kinder)."""
    import backend.api.routes.aktueller_monat as am
    from backend.models import Investition
    from sqlalchemy import select

    monkeypatch.setattr(am, "datetime", _FesteUhr)
    aid, s1, s2, bkw = await _seed(db, mit_bkw=True)
    for inv in (await db.execute(select(Investition).where(Investition.id.in_([s1, s2])))).scalars().all():
        inv.parent_investition_id = bkw
    await db.commit()
    info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, abdeckung_von=None)
    _quellen_still(am, monkeypatch, {
        "pv_erzeugung_kwh": (ANLAGENZAEHLER, info),
        "einspeisung_kwh": (400.0, info),
        "netzbezug_kwh": (200.0, info),
        f"inv_{s1}_pv_erzeugung_kwh": (550.0, info),
        f"inv_{s2}_pv_erzeugung_kwh": (380.0, info),
        f"inv_{bkw}_pv_erzeugung_kwh": (930.0, info),
    })
    res = await am.get_aktueller_monat(anlage_id=aid, jahr=JETZT.year, monat=JETZT.month, db=db)
    assert res.pv_erzeugung_kwh == 930.0
