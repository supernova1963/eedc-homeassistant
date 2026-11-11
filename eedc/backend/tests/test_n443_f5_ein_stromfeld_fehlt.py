"""N-443 — bei getrennter Strommessung fehlt EINE Stromseite, der Checker schwieg.

**Der Defekt.** `_check_wp_monatsdaten` verknüpfte die zwei Stromfelder einer
F5-Anlage mit `and`: ein Monat landete nur dann in `fehlend_strom`, wenn
`strom_heizen_kwh` **und** `strom_warmwasser_kwh` leer waren. Fehlte nur eine
Seite, während die zugehörige Wärme gepflegt ist, gab es **keine** Meldung —
und die Gesamt-Arbeitszahl rechnet dann die Wärme **beider** Seiten über den
Strom **einer**.

**Gemessen (Fall L, Sitzung 204, hier nachgestellt):** ein F5-Gerät, ein Monat,
Heizwärme 1800 + Heizstrom 600 + Warmwasser-Wärme 600 **ohne** Warmwasser-Strom
⇒ Arbeitszahl **4,0** (2400 ÷ 600) ohne jeden Grund daneben, Checker still.

⛔ **Keine Sperre an der Zahl** (Tor-3-Doktrin, 29.08.: fehlende Zuordnung ⇒
nichts an der Zahl, der Checker nennt den Weg). Gebaut ist ausschließlich der
**Melder** — und zwar der bestehende, geschärft (N-346-Lehre: kein zweiter Turm).

**Schwesterdateien:** `test_b5_strom_warmwasser_luft_luft.py` (dieselbe
Bedingung, die Klimaanlagen-Hälfte — ihre Proben halten den Bestand),
`test_b2_daten_checker_registry.py` (die Registry hinter `ww_strom_gibt_es`),
`test_daten_checker_wp_arbeitszahl.py` (der Plausibilitäts-Prüfer, der bei 4,0
schweigt — seine Schwelle liegt bei 7,0).

Self-contained:

    eedc/backend/venv/bin/python -m pytest \
        eedc/backend/tests/test_n443_f5_ein_stromfeld_fehlt.py
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_link
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Auf Modulebene, damit `Base.metadata.create_all` in der `db`-Fixture die
# Tabellen kennt — ein Import erst IM Test kommt dafür zu spät.
from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)
from backend.services.daten_checker import CheckSeverity, DatenChecker

#: Klassische Wärmepumpe mit getrennter Strommessung — beide Seiten der Achse.
WP_GETRENNT = {"wp_art": "luft_wasser", "getrennte_strommessung": True}
#: Split-Klimaanlage: kein Warmwasserkreis (N-304/B5), also auch kein
#: Warmwasser-Strom.
KLIMA_GETRENNT = {"wp_art": "luft_luft", "getrennte_strommessung": True}


async def _wp_befunde(db, *, parameter: dict, monate: dict[int, dict | None]) -> list:
    """Checker-Befunde einer WP mit den Monatszeilen aus `monate` (Monat → Zeile).

    Harness wie in `test_b5_strom_warmwasser_luft_luft.py` — dieselbe Fläche,
    dieselbe Aufrufform.

    ⚠ Nur `_check_wp_monatsdaten`, bewusst ohne
    `_check_werte_in_nicht_gefuehrten_feldern`: der gespeicherte
    Warmwasser-Wert an der Klimaanlage (Probe d) erzeugt dort eine eigene INFO
    (N-393), und die gehört einem anderen Fund. Diese Datei prüft die
    Strom-Meldung.
    """
    anlage = Anlage(anlagenname="N-443", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    for monat, zeile in monate.items():
        if zeile is not None:
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=2025, monat=monat,
                verbrauch_daten=zeile,
            ))
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=200.0, netzbezug_kwh=150.0))
    await db.commit()

    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    wp = next(i for i in geladen.investitionen if i.typ == "waermepumpe")
    # ⚠ Die erwarteten Monate kommen aus der ANLAGEN-Liste, nicht aus der
    # Investition. Ein leeres `[]` an dieser Stelle liefert null Befunde — die
    # Probe wäre gegenstandslos und trotzdem grün.
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    assert monatsdaten, "ohne Anlagen-Monatszeile prueft der Check gar nichts"
    return DatenChecker(db)._check_wp_monatsdaten(
        wp, wp.bezeichnung, wp.parameter, monatsdaten,
    )


def _strom_meldungen(ergebnisse: list) -> list:
    return [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]


# ── Die Folge, an Einzelwerten der Lesetüren gemessen ───────────────────────


def test_die_gesamt_arbeitszahl_rechnet_mit_halbem_nenner():
    """**Warum der Melder gebraucht wird** — die Zahl entsteht aus echten Türen.

    Kein nachgebildeter Quotient: `get_wp_strom_kwh` und die beiden
    Wärme-Lesetüren sind dieselben, aus denen Kachel, Cockpit und der
    Plausibilitäts-Prüfer ihre Werte holen.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl
    from backend.core.field_definitions import (
        get_wp_heizenergie_kwh, get_wp_strom_kwh, get_wp_warmwasser_kwh,
    )

    fall_l = {
        "heizenergie_kwh": 1800.0,
        "strom_heizen_kwh": 600.0,
        "warmwasser_kwh": 600.0,
        # `strom_warmwasser_kwh` fehlt — genau das ist der Fall.
    }
    assert get_wp_strom_kwh(fall_l, WP_GETRENNT) == pytest.approx(600.0)
    assert get_wp_heizenergie_kwh(fall_l) == pytest.approx(1800.0)
    assert get_wp_warmwasser_kwh(fall_l, WP_GETRENNT) == pytest.approx(600.0)

    az = arbeitszahl(1800.0 + 600.0, 600.0)
    assert az.wert == pytest.approx(4.0), (
        "Die Wärme BEIDER Seiten über dem Strom EINER — und 4,0 sieht plausibel "
        "aus, weshalb kein Plausibilitäts-Prüfer sie fängt."
    )


def test_der_plausibilitaets_pruefer_faengt_diesen_fall_nicht():
    """Tor 3, gemessen statt behauptet: 4,0 liegt unter seiner Schwelle 7,0.

    Ohne diese Probe wäre „kein zweiter Turm" eine Behauptung.
    """
    from types import SimpleNamespace

    from backend.services.daten_checker.waermepumpe import WaermepumpeChecks

    imd = SimpleNamespace(jahr=2025, monat=1, verbrauch_daten={
        "heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
        "warmwasser_kwh": 600.0,
    })
    inv = SimpleNamespace(id=1, typ="waermepumpe", bezeichnung="WP",
                          monatsdaten=[imd], parameter=WP_GETRENNT)
    anlage = SimpleNamespace(investitionen=[inv])
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(anlage) == []
    assert WaermepumpeChecks.ARBEITSZAHL_AUFFAELLIG == 7.0


def test_der_von_der_meldung_zitierte_sperrgrund_stimmt():
    """Der Meldungstext zitiert eine ANDERE Fläche — dann muss er sie treffen.

    Er sagt: die Zeile dieser Funktion nennt den Grund bereits („kein
    Stromverbrauch erfasst"), nur die Gesamtzahl kann es nicht. Ohne diese Probe
    wäre das eine Behauptung, die still veraltet, sobald der Layer seinen
    Wortlaut ändert — und dann stünde in der Meldung ein Zitat, das nirgends
    steht (N-86-Klasse: zwei Flächen, verschiedene Aussage).
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl_je_funktion

    ohne_ww_strom = arbeitszahl_je_funktion(
        heizung_kwh=1800.0, strom_heizen_kwh=600.0,
        warmwasser_kwh=600.0, strom_warmwasser_kwh=None, hat_split=True,
    )
    assert ohne_ww_strom.warmwasser.wert is None
    assert ohne_ww_strom.warmwasser.grund == "kein Stromverbrauch erfasst"
    assert ohne_ww_strom.heizen.wert == pytest.approx(3.0)

    ohne_heizstrom = arbeitszahl_je_funktion(
        heizung_kwh=1800.0, strom_heizen_kwh=None,
        warmwasser_kwh=600.0, strom_warmwasser_kwh=200.0, hat_split=True,
    )
    assert ohne_heizstrom.heizen.grund == "kein Stromverbrauch erfasst"


# ── (a) Warmwasser-Wärme ohne Warmwasser-Strom ──────────────────────────────


async def test_a_warmwasser_waerme_ohne_warmwasser_strom_wird_gemeldet(db):
    """Fall L selbst — zwei Monate, damit Zählung und Monatsliste mitgeprüft sind."""
    zeile = {"heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
             "warmwasser_kwh": 600.0}
    ergebnisse = await _wp_befunde(
        db, parameter=WP_GETRENNT, monate={1: dict(zeile), 2: dict(zeile)},
    )
    strom = _strom_meldungen(ergebnisse)
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert strom[0].meldung == "WP: Strom Warmwasser fehlt in 2 Monat(en)"
    assert strom[0].schwere == CheckSeverity.WARNING
    assert "01/2025" in strom[0].details and "02/2025" in strom[0].details
    assert "Nenner" in strom[0].details, (
        "Der Text muss die Folge nennen, nicht nur den Zustand."
    )
    assert "kein Stromverbrauch erfasst" in strom[0].details, (
        "Das Zitat der Funktions-Zeile gehört dazu — s. die Probe darüber."
    )
    assert "Monatsabschluss" in strom[0].details, "Der Handgriff gehört dazu."
    # N-456: Seit die Zuordnungs-Fläche dasselbe Feld als Pflicht führt, darf
    # der Text auch dorthin verweisen — vorher hätte er den Anwender auf eine
    # Fläche geschickt, die ihm sagt, es sei nichts einzutragen.
    assert "in den Datenquellen zu" in strom[0].details, (  # E4: ohne Menüweg-Pfeil
        "Der zweite Weg gehört dazu, seit er nicht mehr ins Leere führt (N-456)."
    )
    assert strom[0].details.index("Monatsabschluss") < strom[0].details.index(
        "in den Datenquellen zu"
    ), "Erst der Weg, der die VERGANGENEN Monate füllt — eine Zuordnung wirkt nach vorn."
    assert befund_link(strom[0]), "Der Weg zum Nachtragen gehört dazu."
    assert strom[0].investition_id, "Ohne sie hängt der Befund an keinem Gerät."
    # Die Heiz-Seite ist vollständig — sie darf nicht mitgemeldet werden.
    assert "Strom Heizen fehlt" not in " ".join(e.meldung for e in ergebnisse)
    assert not [e for e in ergebnisse if e.schwere == CheckSeverity.OK], (
        "Neben der Warnung darf keine OK-Zeile „Monatsdaten vollständig“ "
        "stehen — genau diese Zusage bekam der Fall bis zum Bau, und zwar "
        "als EINZIGEN Befund."
    )


# ── (b) Heizwärme ohne Heizstrom (Gegenrichtung) ────────────────────────────


async def test_b_heizwaerme_ohne_heizstrom_wird_gemeldet(db):
    """Dieselbe Bedingung, andere Seite — sie hing am selben `and`."""
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "warmwasser_kwh": 600.0,
        "strom_warmwasser_kwh": 200.0,
    }})
    strom = _strom_meldungen(ergebnisse)
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert strom[0].meldung == "WP: Strom Heizen fehlt in 1 Monat(en)"
    assert strom[0].schwere == CheckSeverity.WARNING
    assert "01/2025" in strom[0].details
    assert "Nenner" in strom[0].details


# ── (c) Beide Seiten leer ⇒ EINE Meldung wie bisher ─────────────────────────


async def test_c_fehlen_beide_bleibt_es_bei_einer_meldung(db):
    """Bestand: kein Doppel, wenn die ganze Stromachse leer ist.

    Ohne diese Probe könnte die Trennung je Seite aus einer Meldung zwei machen
    — für den Anwender derselbe Sachverhalt, zweimal genannt.
    """
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "warmwasser_kwh": 600.0,
    }})
    strom = _strom_meldungen(ergebnisse)
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert strom[0].meldung == "WP: Strom Heizen/Warmwasser fehlt in 1 Monat(en)"


# ── (d) Die Klimaanlage hat keine Warmwasser-Seite (B5/N-304) ───────────────


async def test_d_klimaanlage_bekommt_keine_warmwasser_meldung(db):
    """Ein an einer Luft-Luft-Anlage GESPEICHERTER Warmwasser-Wert zieht nicht.

    Genau der Wert aus N-379 (dietmar1968, 889 kWh „Warmwasser" an einer
    Klimaanlage): Das Gerät hat den Warmwasserkreis nicht, `strom_warmwasser_kwh`
    wird im Monatsabschluss gar nicht angeboten — ihn anzumahnen wäre ein
    Hinweis, den der Anwender nicht auflösen kann (N-86-Klasse: dieselbe
    Anlage, zwei Flächen, gegenteilige Aussage).
    """
    ergebnisse = await _wp_befunde(db, parameter=KLIMA_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
        "warmwasser_kwh": 889.0,
    }})
    assert not _strom_meldungen(ergebnisse), [e.meldung for e in ergebnisse]


# ── (e) Kein Betrieb ist kein fehlendes Feld ────────────────────────────────


async def test_e_ohne_warmwasser_waerme_bleibt_es_still(db):
    """Ein Monat ohne Warmwasser-Abgabe braucht keinen Warmwasser-Strom.

    Die Klausel hängt an der **Wärme**, nicht an der bloßen Anwesenheit des
    Feldes — sonst meldete eedc jeder reinen Heiz-Anlage zwölf Lücken im Jahr.
    """
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
    }})
    assert not _strom_meldungen(ergebnisse), [e.meldung for e in ergebnisse]


async def test_e3_der_sommermonat_ohne_heizung_bleibt_still(db):
    """Die Gegenrichtung derselben Klausel — und die häufigere Lage.

    Juli: die Anlage macht nur Warmwasser, Heizwärme und Heizstrom stehen beide
    leer. Ohne die Wärme-Bedingung meldete eedc hier „Strom Heizen fehlt" —
    jeder Anlage, jeden Sommer.
    """
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={7: {
        "warmwasser_kwh": 600.0, "strom_warmwasser_kwh": 200.0,
    }})
    assert not _strom_meldungen(ergebnisse), [e.meldung for e in ergebnisse]


async def test_e2_eine_gepflegte_null_ist_kein_betrieb(db):
    """Dieselbe Klausel, die andere Schreibweise von „nichts abgegeben"."""
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
        "warmwasser_kwh": 0.0,
    }})
    assert not _strom_meldungen(ergebnisse), [e.meldung for e in ergebnisse]


# ── (f) Der vollständige Monat schweigt ─────────────────────────────────────


async def test_f_ein_vollstaendiger_monat_meldet_nichts(db):
    """Gegenprobe — ohne sie belegen die Proben darüber nur, dass irgendetwas kommt."""
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, monate={1: {
        "heizenergie_kwh": 1800.0, "strom_heizen_kwh": 600.0,
        "warmwasser_kwh": 600.0, "strom_warmwasser_kwh": 200.0,
    }})
    assert not _strom_meldungen(ergebnisse), [e.meldung for e in ergebnisse]
    assert [e for e in ergebnisse if e.schwere == CheckSeverity.OK], (
        "Ein vollständiger Monat meldet die OK-Zeile — sonst ist die Probe "
        "auch dann grün, wenn der Check gar nicht lief."
    )
