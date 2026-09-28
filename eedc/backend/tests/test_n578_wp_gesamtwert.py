"""N-578 B2a — die Summen-Marke des WP-Gesamtstroms (#416, Rainer).

Das Monatsformular rechnet bei getrennter Strommessung den Gesamtstrom selbst
(`strom_heizen_kwh + strom_warmwasser_kwh`) und schickt ihn seit N-578 mit der
Marke ``summe_achsen`` über den #352-Kanal ``abgeleitet_felder``. Hier steht die
Backend-Hälfte: die Positivliste nimmt die Marke an — **nur** am Feld
``stromverbrauch_kwh`` —, und die Speicherroute legt sie in die Provenance des
Sub-Keys, nicht in ``verbrauch_daten``.

⚠ **Warum die Marke an ihr Feld gebunden ist:** ``pv_monatswerte.py`` und
``daten_checker/energieprofil.py`` werten an ``pv_erzeugung_kwh`` die bloße
*Anwesenheit* einer Marke aus (kWp-Zerlegung). ``summe_achsen`` dort machte aus
einer Messung still eine Verteilung.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.api.routes.monatsdaten import _save_investitionen_monatsdaten
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.provenance import (
    ABGELEITET_KWP_ANTEIL,
    ABGELEITET_SUMME_ACHSEN,
    gepruefte_ableitung,
    gepruefte_ableitungen,
)

_KEY = "verbrauch_daten.stromverbrauch_kwh"


def test_marke_wird_am_gesamtstrom_angenommen():
    assert gepruefte_ableitungen(
        {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN}
    ) == {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN}


def test_marke_an_einem_fremden_feld_wird_verworfen():
    """Gegenrichtung: dieselbe Marke am PV-Feld machte eine Messung zur Zerlegung."""
    assert gepruefte_ableitungen({"pv_erzeugung_kwh": ABGELEITET_SUMME_ACHSEN}) == {}
    # Die älteren Marken bleiben ungebunden — ihr Vertrag ändert sich nicht.
    assert gepruefte_ableitungen(
        {"pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL}
    ) == {"pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL}


def test_ohne_feld_wird_die_gebundene_marke_verworfen():
    """Der Wizard-Endpunkt ruft ohne Feld (kein Client-Aufrufer mehr)."""
    assert gepruefte_ableitung(ABGELEITET_SUMME_ACHSEN) is None
    assert gepruefte_ableitung(ABGELEITET_SUMME_ACHSEN, feld="stromverbrauch_kwh") == (
        ABGELEITET_SUMME_ACHSEN
    )


async def _wp(db) -> Investition:
    anlage = Anlage(anlagenname="N578", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"wp_art": "luft_wasser", "getrennte_strommessung": True},
    )
    db.add(inv)
    await db.flush()
    return inv


async def _zeile(db, inv_id: int) -> InvestitionMonatsdaten:
    return (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == inv_id)
    )).scalar_one()


async def test_erstspeicherung_legt_die_marke_in_die_provenance(db):
    """INSERT-Zweig (`seed_provenance`): Marke am Sub-Key, Nutz-Dict ohne Metadaten."""
    inv = await _wp(db)
    await db.commit()
    await _save_investitionen_monatsdaten(db, {
        str(inv.id): {
            "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 10.0, "stromverbrauch_kwh": 11.0,
            "abgeleitet_felder": {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN},
        },
    }, 2026, 9)
    await db.commit()
    imd = await _zeile(db, inv.id)
    assert imd.verbrauch_daten == {
        "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 10.0, "stromverbrauch_kwh": 11.0,
    }
    assert imd.source_provenance[_KEY]["abgeleitet"] == ABGELEITET_SUMME_ACHSEN
    # Die Achsen sind Messungen und bleiben unmarkiert.
    assert "abgeleitet" not in imd.source_provenance["verbrauch_daten.strom_heizen_kwh"]


async def test_folgespeicherung_ersetzt_den_eingefrorenen_wert_und_markiert_ihn(db):
    """UPDATE-Zweig: Rainers Monat — gespeichert 20 ohne Marke, jetzt 41 als Summe."""
    inv = await _wp(db)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=9,
        verbrauch_daten={"strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 31.0, "stromverbrauch_kwh": 20.0},
        source_provenance={},
    ))
    await db.commit()
    await _save_investitionen_monatsdaten(db, {
        str(inv.id): {
            "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 40.0, "stromverbrauch_kwh": 41.0,
            "abgeleitet_felder": {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN},
        },
    }, 2026, 9)
    await db.commit()
    imd = await _zeile(db, inv.id)
    assert imd.verbrauch_daten["stromverbrauch_kwh"] == 41.0
    assert imd.source_provenance[_KEY]["abgeleitet"] == ABGELEITET_SUMME_ACHSEN


async def test_ein_gepflegter_wert_danach_verliert_die_marke(db):
    """Die Marke gehört zum Wert: tippt der Anwender einen eigenen Gesamtwert, ist er handgepflegt."""
    inv = await _wp(db)
    await db.commit()
    await _save_investitionen_monatsdaten(db, {
        str(inv.id): {
            "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 10.0, "stromverbrauch_kwh": 11.0,
            "abgeleitet_felder": {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN},
        },
    }, 2026, 9)
    await db.commit()
    await _save_investitionen_monatsdaten(db, {
        str(inv.id): {"strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 10.0, "stromverbrauch_kwh": 13.5},
    }, 2026, 9)
    await db.commit()
    imd = await _zeile(db, inv.id)
    assert imd.verbrauch_daten["stromverbrauch_kwh"] == 13.5
    assert "abgeleitet" not in imd.source_provenance[_KEY]


# ═══════════════════════════════════════════════════════════════════════════
# B2a Leseseite (H1) — die Laderoute des Formulars liefert die Marken mit
# ═══════════════════════════════════════════════════════════════════════════


async def test_laderoute_liefert_die_marke_je_zeile(db):
    """Das Formular entscheidet beim Laden — ohne den Status (Herkunft F5)."""
    from backend.api.routes.investitionen.dashboards import get_investition_monatsdaten_by_month

    inv = await _wp(db)
    await db.commit()
    await _save_investitionen_monatsdaten(db, {
        str(inv.id): {
            "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 10.0, "stromverbrauch_kwh": 11.0,
            "abgeleitet_felder": {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN},
        },
    }, 2026, 9)
    await db.commit()
    zeilen = await get_investition_monatsdaten_by_month(inv.anlage_id, 2026, 9, db)
    assert len(zeilen) == 1
    assert zeilen[0].abgeleitet_felder == {"stromverbrauch_kwh": ABGELEITET_SUMME_ACHSEN}
    assert zeilen[0].verbrauch_daten["stromverbrauch_kwh"] == 11.0


async def test_laderoute_ohne_marke_liefert_leeres_dict_und_bleibt_sonst_gleich(db):
    """Additiv: dieselben Felder wie bisher plus `abgeleitet_felder`."""
    from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse
    from backend.api.routes.investitionen.dashboards import get_investition_monatsdaten_by_month

    inv = await _wp(db)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=9,
        verbrauch_daten={"strom_heizen_kwh": 1.0, "stromverbrauch_kwh": 50.0}, source_provenance={},
    ))
    await db.commit()
    zeilen = await get_investition_monatsdaten_by_month(inv.anlage_id, 2026, 9, db)
    dump = zeilen[0].model_dump()
    assert dump["abgeleitet_felder"] == {}
    assert set(dump) == set(InvestitionMonatsdatenResponse.model_fields) | {"abgeleitet_felder"}
    # Die Dashboards liefern das geteilte Modell — dort kein neues Feld.
    assert "abgeleitet_felder" not in InvestitionMonatsdatenResponse.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# H3 (Master-Entscheid) — keine neue Meldung, eine zweite Deutung an den
# bestehenden, nur bei unmarkierten `manual:form`-Werten
# ═══════════════════════════════════════════════════════════════════════════

_HANDGRIFF = "Leere dann im Monatsformular das Feld „Stromverbrauch“"


async def _checker(db, zeile: dict, provenance: dict) -> list:
    from sqlalchemy.orm import selectinload

    from backend.models import Monatsdaten
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="N578-H3", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=20000.0,
        parameter={"wp_art": "luft_wasser", "getrennte_strommessung": True},
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2025, monat=6,
        verbrauch_daten={**zeile, "heizenergie_kwh": 3000.0, "warmwasser_kwh": 600.0},
        source_provenance=provenance,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6, einspeisung_kwh=200.0, netzbezug_kwh=150.0))
    await db.commit()
    geladen = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    wp = geladen.investitionen[0]
    return DatenChecker(db)._check_wp_monatsdaten(wp, wp.bezeichnung, wp.parameter, monatsdaten)


def _formular(marke: str | None = None) -> dict:
    eintrag = {"source": "manual:form", "writer": "t", "at": "2025-07-01T00:00:00Z"}
    if marke:
        eintrag["abgeleitet"] = marke
    return {"verbrauch_daten.stromverbrauch_kwh": eintrag}


_IMPORT = {"verbrauch_daten.stromverbrauch_kwh": {"source": "external:ha_statistics", "writer": "t", "at": "x"}}
_UNTER = {"stromverbrauch_kwh": 20.0, "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 31.0}


async def test_h3_unter_der_summe_aus_dem_formular_nennt_den_handgriff(db):
    """Rainers Monat: die bestehende Warnung — und jetzt die zweite Deutung dazu."""
    ergebnisse = await _checker(db, _UNTER, _formular())
    warnung = [e for e in ergebnisse if "kleiner als die Summe der Achsen" in e.meldung]
    assert len(warnung) == 1
    assert _HANDGRIFF in warnung[0].details
    assert "06/2025" in warnung[0].details


async def test_h3_ein_importierter_wert_bekommt_den_satz_nicht(db):
    """Gegenrichtung: ein Sensor-/Import-Wert ist gemessen, nicht eingefroren."""
    ergebnisse = await _checker(db, _UNTER, _IMPORT)
    warnung = [e for e in ergebnisse if "kleiner als die Summe der Achsen" in e.meldung]
    assert len(warnung) == 1
    assert _HANDGRIFF not in warnung[0].details


async def test_h3_die_eigene_summe_bekommt_den_satz_nicht(db):
    """Eine markierte Auto-Summe rechnet beim nächsten Speichern ohnehin neu."""
    ergebnisse = await _checker(db, _UNTER, _formular(ABGELEITET_SUMME_ACHSEN))
    warnung = [e for e in ergebnisse if "kleiner als die Summe der Achsen" in e.meldung]
    assert len(warnung) == 1
    assert _HANDGRIFF not in warnung[0].details


async def test_h3_rest_ueber_25_prozent_aus_dem_formular_nennt_den_handgriff(db):
    """Die zweite bestehende Meldung (WK-16d D1) — die still zu hohe Richtung."""
    ergebnisse = await _checker(db, {
        "stromverbrauch_kwh": 81.0, "strom_heizen_kwh": 1.0, "strom_warmwasser_kwh": 31.0,
    }, _formular())
    frage = [e for e in ergebnisse if "misst deutlich mehr" in e.meldung]
    assert len(frage) == 1
    assert _HANDGRIFF in frage[0].details


async def test_h3_keine_neue_meldung_unter_25_prozent(db):
    """WK-16d D2 bleibt: dietmar1968s 6,6 % Standby sind keine Frage — auch aus dem Formular nicht."""
    mit = await _checker(db, {
        "stromverbrauch_kwh": 2193.0, "strom_heizen_kwh": 1500.0, "strom_warmwasser_kwh": 548.0,
    }, _formular())
    assert not [e for e in mit if "misst deutlich mehr" in e.meldung or "kleiner als die Summe" in e.meldung]
    assert not [e for e in mit if _HANDGRIFF in (e.details or "")]
