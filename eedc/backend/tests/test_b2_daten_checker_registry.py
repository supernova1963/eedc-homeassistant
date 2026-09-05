"""B2 — der Daten-Checker fragt die Registry, nicht die Bauart (SOLL Wärme/Klima R1).

Matrix-Durchgang Paket 2. Vier Stellen entschieden bis 05.09.2026 nach
`ist_luft_luft_waermepumpe`: welche Zähler erwartet werden (Abdeckung), wann zu
Zusatz-Zählern geschwiegen wird, ob Heizwärme fehlt und wie das Strom-Label
heißt. Jede Stelle war für die Klimaanlage richtig — und für die
Brauchwasser-Wärmepumpe (A6) falsch: sie hätte einen Heizstrom-Zähler liefern
und Heizwärme pflegen müssen, die dieselbe Registry hinter „Weitere Größen
erfassen" stellt. *Dieselbe Anlage, zwei Flächen, gegenteilige Aussage.*

Jetzt kommt die Antwort aus der Registry (`feld_urteil` · `feld_herabgestuft` ·
`pflicht_felder_am_geraet` · `get_feld_bedarf`), und ein erweitertes Feld ist
nie Pflicht. Der Modus-Hinweis wählt seine Geräte nach Bauart-VORSCHLAG plus
Kühl-BELEGLAGE — eine Luft-Wasser-Wärmepumpe mit Kühlfunktion bekommt ihn jetzt
auch (MartyBr, T89667 #199).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.field_definitions import (
    URTEIL_ERWEITERT,
    URTEIL_GILT,
    URTEIL_NEIN,
    feld_herabgestuft,
    feld_urteil,
    get_feld_bedarf,
    pflicht_felder_am_geraet,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.daten_checker import DatenChecker

LUFT_WASSER = {"wp_art": "luft_wasser"}
KLIMA = {"wp_art": "luft_luft"}
BRAUCHWASSER = {"wp_art": "brauchwasser"}
GETRENNT = {"getrennte_strommessung": True}


# ── Die Registry ────────────────────────────────────────────────────────────

def test_feld_urteil_kennt_alle_drei_ausgaenge():
    assert feld_urteil("waermepumpe", "warmwasser_kwh", LUFT_WASSER) == URTEIL_GILT
    assert feld_urteil("waermepumpe", "warmwasser_kwh", KLIMA) == URTEIL_NEIN
    assert feld_urteil("waermepumpe", "heizenergie_kwh", BRAUCHWASSER) == URTEIL_ERWEITERT
    assert feld_urteil("waermepumpe", "strom_heizen_kwh", {**BRAUCHWASSER, **GETRENNT}) == URTEIL_ERWEITERT
    assert feld_urteil("waermepumpe", "strom_heizen_kwh", LUFT_WASSER) == URTEIL_NEIN, "ohne getrennte Messung gibt es die Achse nicht"
    assert feld_urteil("waermepumpe", "gibt_es_nicht", KLIMA) == URTEIL_GILT, "fail-open wie die Nachbarn"
    assert feld_urteil("waermepumpe", "betriebsart_strom_kuehlen_kwh-3", LUFT_WASSER) == URTEIL_ERWEITERT, "Innengeräte-Suffix wird aufgelöst"


def test_ein_erweitertes_feld_ist_nie_pflicht():
    """Bis B2: `strom_heizen_kwh` an einer Brauchwasser-WP galt als Pflicht, obwohl die
    Registry es hinter „Weitere Größen erfassen" stellte."""
    assert get_feld_bedarf("waermepumpe", "strom_heizen_kwh", {**LUFT_WASSER, **GETRENNT})[0] == "pflicht"
    assert get_feld_bedarf("waermepumpe", "strom_heizen_kwh", {**BRAUCHWASSER, **GETRENNT})[0] == "optional"
    assert get_feld_bedarf("waermepumpe", "heizenergie_kwh", BRAUCHWASSER)[0] == "optional"
    # Die bekannten Einstufungen bleiben.
    assert get_feld_bedarf("waermepumpe", "heizenergie_kwh", LUFT_WASSER)[0] == "pflicht"
    assert get_feld_bedarf("waermepumpe", "heizenergie_kwh", KLIMA)[0] == "optional"
    assert get_feld_bedarf("waermepumpe", "heizenergie_kwh", None)[0] == "pflicht", "ohne Gerät: die Typ-Einstufung"


def test_feld_herabgestuft_ist_die_frage_des_zusatz_hinweises():
    # Luft-Wasser: nichts herabgestuft — beide Wärmegrößen werden erwartet.
    assert feld_herabgestuft("waermepumpe", "heizenergie_kwh", LUFT_WASSER) is False
    assert feld_herabgestuft("waermepumpe", "warmwasser_kwh", LUFT_WASSER) is False
    # Klimaanlage: Heizwärme optional (KLIMA_OHNE_WAERMEMENGE), Warmwasser nicht vorhanden.
    assert feld_herabgestuft("waermepumpe", "heizenergie_kwh", KLIMA) is True
    assert feld_herabgestuft("waermepumpe", "warmwasser_kwh", KLIMA) is True
    # Brauchwasser: Heizwärme erweitert, Warmwasser erwartet.
    assert feld_herabgestuft("waermepumpe", "heizenergie_kwh", BRAUCHWASSER) is True
    assert feld_herabgestuft("waermepumpe", "warmwasser_kwh", BRAUCHWASSER) is False
    # Altbestand ohne Art: klassische Wärmepumpe.
    assert feld_herabgestuft("waermepumpe", "heizenergie_kwh", {}) is False


def test_pflicht_felder_je_geraet_ohne_if_wp_art():
    assert pflicht_felder_am_geraet("waermepumpe", LUFT_WASSER) == ["stromverbrauch_kwh", "heizenergie_kwh"]
    z = lambda p: pflicht_felder_am_geraet("waermepumpe", p, gruppe="wp_strom")  # noqa: E731
    assert z(LUFT_WASSER) == ["stromverbrauch_kwh"], "die Zählerfrage kennt keine Heizwärme"
    assert z({**LUFT_WASSER, **GETRENNT}) == ["strom_heizen_kwh", "strom_warmwasser_kwh"]
    assert z({**KLIMA, **GETRENNT}) == ["strom_heizen_kwh"]
    assert z(KLIMA) == ["stromverbrauch_kwh"]
    assert z({**BRAUCHWASSER, **GETRENNT}) == ["strom_warmwasser_kwh"]
    assert pflicht_felder_am_geraet("speicher", {}) == ["ladung_kwh", "entladung_kwh"]
    assert pflicht_felder_am_geraet("sonstiges", {}) == [], "Sonstiges ist kategorieabhängig — nicht hier"


# ── Die Checker ─────────────────────────────────────────────────────────────

async def _anlage(db, parameter: dict, *, mapping_felder: dict | None = None,
                  live: dict | None = None, imd: dict | None = None, mit_monat: bool = False):
    anlage = Anlage(anlagenname="B2", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0, parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    eintrag: dict = {}
    if mapping_felder:
        eintrag["felder"] = {f: {"strategie": "sensor", "sensor_id": f"sensor.{f}"} for f in mapping_felder}
    if live:
        eintrag["live"] = live
    anlage.sensor_mapping = {"investitionen": {str(inv.id): eintrag}} if eintrag else {}
    if imd is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2025, monat=1, verbrauch_daten=imd))
    if mit_monat:
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1, einspeisung_kwh=1.0, netzbezug_kwh=1.0))
    await db.commit()
    geladen = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    return geladen, next(i for i in geladen.investitionen)


def _abdeckung_fehlend(db, anlage) -> list[str]:
    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    return [e.details or "" for e in erg if "ohne Abdeckung" in e.meldung or "Komponente" in e.meldung and e.schwere == "warning"]


@pytest.mark.asyncio
async def test_abdeckung_luft_wasser_ohne_wmz_bekommt_keine_warnung(db):
    """Die Zählerfrage der Abdeckung ist der STROM — Heizwärme ist Pflicht, aber
    ein Zusatz-Zähler (INFO, s. Zusatz-Hinweis), keine Abdeckungs-Warnung."""
    anlage, _ = await _anlage(db, LUFT_WASSER, mapping_felder=["stromverbrauch_kwh"])
    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    assert not any(e.schwere == "warning" and "WP" in (e.details or "") for e in erg)


@pytest.mark.asyncio
async def test_abdeckung_brauchwasser_erwartet_nur_den_warmwasser_strom(db):
    """Bis B2 verlangte die Abdeckung `strom_heizen_kwh` an einer Brauchwasser-WP."""
    anlage, _ = await _anlage(db, {**BRAUCHWASSER, **GETRENNT}, mapping_felder=["strom_warmwasser_kwh"])
    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    assert not any("strom_heizen_kwh" in (e.details or "") for e in erg)
    assert not any(e.schwere == "warning" and "WP" in (e.details or "") for e in erg)


@pytest.mark.asyncio
async def test_abdeckung_klima_erwartet_keinen_warmwasser_strom_und_luft_wasser_beide(db):
    anlage_k, _ = await _anlage(db, {**KLIMA, **GETRENNT}, mapping_felder=["strom_heizen_kwh"])
    erg_k = DatenChecker(db)._check_energieprofil_abdeckung(anlage_k, [])
    assert not any("strom_warmwasser_kwh" in (e.details or "") for e in erg_k)
    anlage_w, _ = await _anlage(db, {**LUFT_WASSER, **GETRENNT}, mapping_felder=["strom_heizen_kwh"])
    erg_w = DatenChecker(db)._check_energieprofil_abdeckung(anlage_w, [])
    assert any("strom_warmwasser_kwh" in (e.details or "") for e in erg_w), "Gegenprobe: die Warmwasser-Seite wird weiter erwartet"


def _zusatz(db, anlage) -> str:
    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    treffer = [e for e in erg if "ohne Zusatz-Zähler" in e.meldung]
    return treffer[0].details if treffer else ""


@pytest.mark.asyncio
async def test_zusatz_hinweis_folgt_der_registry_nicht_der_bauart(db):
    anlage_w, _ = await _anlage(db, LUFT_WASSER)
    assert "WP: Heizwärme, Warmwasser" in _zusatz(db, anlage_w)
    anlage_k, _ = await _anlage(db, KLIMA)
    assert _zusatz(db, anlage_k) == "", "Klimaanlage: beide Wärmegrößen herabgestuft — kein Hinweis"
    anlage_b, _ = await _anlage(db, BRAUCHWASSER)
    assert "WP: Warmwasser" in _zusatz(db, anlage_b), "Brauchwasser-WP: ihre Wärme ist das Warmwasser"
    assert "Heizwärme" not in _zusatz(db, anlage_b), "… und nach Heizwärme wird sie nicht gefragt"


@pytest.mark.asyncio
async def test_heizwaerme_fehlt_nur_wo_sie_erwartet_wird(db):
    anlage_b, inv_b = await _anlage(db, BRAUCHWASSER, imd={"stromverbrauch_kwh": 50.0}, mit_monat=True)
    monatsdaten = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_b.id))).scalars())
    erg_b = DatenChecker(db)._check_wp_monatsdaten(inv_b, "WP", inv_b.parameter, monatsdaten)
    assert not [e for e in erg_b if "Heizwärme fehlt" in e.meldung], "Brauchwasser-WP: Heizwärme ist erweitert"
    anlage_w, inv_w = await _anlage(db, LUFT_WASSER, imd={"stromverbrauch_kwh": 50.0}, mit_monat=True)
    monatsdaten = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_w.id))).scalars())
    erg_w = DatenChecker(db)._check_wp_monatsdaten(inv_w, "WP", inv_w.parameter, monatsdaten)
    assert [e for e in erg_w if "Heizwärme fehlt" in e.meldung], "Gegenprobe: an der Luft-Wasser-WP weiterhin"


@pytest.mark.asyncio
async def test_strom_label_folgt_der_warmwasser_seite(db):
    anlage_k, inv_k = await _anlage(db, {**KLIMA, **GETRENNT}, imd={}, mit_monat=True)
    monatsdaten = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_k.id))).scalars())
    erg = DatenChecker(db)._check_wp_monatsdaten(inv_k, "WP", inv_k.parameter, monatsdaten)
    fehlt = [e for e in erg if "fehlt in" in e.meldung and "Strom" in e.meldung]
    assert fehlt and "Strom Heizen fehlt" in fehlt[0].meldung and "Warmwasser" not in fehlt[0].meldung


# ── Der Modus-Hinweis: Bauart schlägt vor, Beleglage ergänzt ────────────────

@pytest.mark.asyncio
async def test_modus_hinweis_luft_wasser_ohne_kuehl_spur_bleibt_still(db):
    anlage, _ = await _anlage(db, LUFT_WASSER, mapping_felder=["stromverbrauch_kwh"])
    assert await DatenChecker(db)._check_klima_modus_sensor(anlage) == []


@pytest.mark.asyncio
async def test_modus_hinweis_luft_wasser_mit_kuehl_leistung_bekommt_ihn(db):
    """MartyBrs Bauform: eine Wärmepumpe, die nachweislich kühlt (Kühl-Leistung live zugeordnet)."""
    anlage, inv = await _anlage(db, LUFT_WASSER, live={"leistung_kuehlen_w": "sensor.wp_kuehl_w"})
    erg = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    assert len(erg) == 1 and "Betriebsmodus nicht zugeordnet" in erg[0].meldung
    assert "Dieses Gerät heizt und kühlt" in erg[0].details
    assert "Klimaanlage" not in erg[0].details, "der Text nennt keine Bauart mehr"


@pytest.mark.asyncio
async def test_modus_hinweis_kuehl_spur_aus_der_monatszeile(db):
    """Kältemenge gepflegt, aber kein Betriebsart-Strom und kein Modus ⇒ Hinweis."""
    anlage, _ = await _anlage(db, LUFT_WASSER, imd={"betriebsart_nutzenergie_kuehlen_kwh": 120.0})
    erg = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    assert len(erg) == 1 and "nicht zugeordnet" in erg[0].meldung


@pytest.mark.asyncio
async def test_modus_hinweis_gemessener_kuehlstrom_ist_schon_eine_aufteilung(db):
    """Kühl-Betriebsart-Zähler gepflegt ⇒ F-60: gemessen, kein Hinweis, eine OK-Zeile."""
    anlage, _ = await _anlage(db, LUFT_WASSER, imd={"betriebsart_strom_kuehlen_kwh": 80.0})
    erg = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    assert len(erg) == 1 and erg[0].schwere == "ok" and "gemessen" in erg[0].meldung.lower()


@pytest.mark.asyncio
async def test_modus_hinweis_klimaanlage_weiterhin_per_vorschlag(db):
    anlage, _ = await _anlage(db, KLIMA, mapping_felder=["stromverbrauch_kwh"])
    erg = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    assert len(erg) == 1 and "nicht zugeordnet" in erg[0].meldung
