"""
Phase 1 Klimaanlage-Erweiterung im WP-Modell (Forum #548 alex_s9027).

Split-Klimaanlagen sind physikalisch Luft-Luft-Wärmepumpen (Reverse-Cycle),
haben aber typischerweise keinen Wärmemengenzähler — nur einen Stromzähler.

Phase 1 macht zwei Anpassungen:
1. Daten-Checker meldet bei `wp_art="luft_luft"` keine "Heizwärme fehlt"-Warnung
   (das ist bei Klimas das normale Verhalten, kein Datenloch).
2. JAZ/COP-Berechnung in den Cockpit-Routes liefert None statt 0, wenn
   wp_strom > 0 aber wp_waerme = 0 (siehe geänderte uebersicht.py / komponenten.py /
   pdf_operations.py / social.py [2026-07-31 zurückgebaut] / jahresbericht.py).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.daten_checker import DatenChecker


async def _reload_anlage(session, anlage_id):
    result = await session.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one()
    monatsdaten = list((await session.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


def _imd(inv_id, jahr, monat, *, stromverbrauch_kwh=None, heizenergie_kwh=None):
    """Hilfs-Konstruktor für InvestitionMonatsdaten."""
    daten = {}
    if stromverbrauch_kwh is not None:
        daten["stromverbrauch_kwh"] = stromverbrauch_kwh
    if heizenergie_kwh is not None:
        daten["heizenergie_kwh"] = heizenergie_kwh
    return InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten=daten,
    )


def test_helper_erkennt_die_klima_in_allen_uebergabeformen():
    """`ist_luft_luft_waermepumpe` — SoT der Unterscheidung (02.08.).

    Bis dahin stand der Vergleich `wp_art == "luft_luft"` als Literal an genau
    einer Stelle; die zweite Stelle (`daten_checker/energieprofil.py`) hat ihn
    schlicht vergessen. Der Helper nimmt — wie `ist_dienstlich` — Objekt,
    Dict oder None.
    """
    from backend.core.investition_parameter import ist_luft_luft_waermepumpe

    class _Inv:
        def __init__(self, parameter):
            self.parameter = parameter

    assert ist_luft_luft_waermepumpe(_Inv({"wp_art": "luft_luft"})) is True
    assert ist_luft_luft_waermepumpe({"wp_art": "luft_luft"}) is True
    assert ist_luft_luft_waermepumpe({"wp_art": " Luft_Luft "}) is True

    assert ist_luft_luft_waermepumpe({"wp_art": "luft_wasser"}) is False
    assert ist_luft_luft_waermepumpe({}) is False, "fehlende Angabe = klassische WP"
    assert ist_luft_luft_waermepumpe(_Inv(None)) is False
    assert ist_luft_luft_waermepumpe(None) is False


async def test_klima_meldet_keine_heizwaerme_warnung(db):
    """Bei wp_art='luft_luft' fehlt die Heizenergie-Warnung im Daten-Checker."""
    anlage = Anlage(
        anlagenname="TestKlima",
        leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    klima = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Daikin Split", anschaffungsdatum=date(2025, 1, 1),
        parameter={"wp_art": "luft_luft"},
    )
    db.add(klima)
    await db.flush()

    # Stromverbrauch vorhanden, Heizenergie NICHT (Klima-Realität)
    for monat in range(1, 6):
        db.add(_imd(klima.id, 2025, monat, stromverbrauch_kwh=100.0))

    # Mindest-Anlagenmonatsdaten, damit Checker läuft
    for monat in range(1, 6):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=200.0, netzbezug_kwh=150.0,
        ))
    await db.commit()

    anlage_loaded, monatsdaten = await _reload_anlage(db, anlage.id)
    klima_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

    checker = DatenChecker(db)
    ergebnisse = checker._check_wp_monatsdaten(
        klima_loaded, "Daikin Split", klima_loaded.parameter, []
    )

    # Es darf KEINE "Heizwärme fehlt"-Meldung kommen
    heiz_warnungen = [
        e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
    ]
    assert not heiz_warnungen, (
        f"Klimaanlage darf keine Heizwärme-Warnung bekommen, "
        f"erhielt aber: {[e.meldung for e in heiz_warnungen]}"
    )


async def test_klassische_wp_meldet_heizwaerme_warnung_weiterhin(db):
    """Bei wp_art='luft_wasser' (Standard-WP) fehlt die Heizwärme-Warnung weiterhin
    wenn heizenergie_kwh nicht vorliegt — kein Regress."""
    anlage = Anlage(
        anlagenname="TestWP",
        leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Vitocal", anschaffungsdatum=date(2025, 1, 1),
        parameter={"wp_art": "luft_wasser"},
    )
    db.add(wp)
    await db.flush()

    for monat in range(1, 6):
        db.add(_imd(wp.id, 2025, monat, stromverbrauch_kwh=100.0))

    for monat in range(1, 6):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=200.0, netzbezug_kwh=150.0,
        ))
    await db.commit()

    anlage_loaded, monatsdaten = await _reload_anlage(db, anlage.id)
    wp_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

    checker = DatenChecker(db)
    ergebnisse = checker._check_wp_monatsdaten(
        wp_loaded, "Vitocal", wp_loaded.parameter, monatsdaten
    )

    heiz_warnungen = [
        e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
    ]
    assert heiz_warnungen, (
        "Klassische Luft-Wasser-WP muss Heizwärme-Warnung bekommen, "
        "wenn heizenergie_kwh fehlt — sonst ist die Klima-Sonderbehandlung "
        "zu breit."
    )


async def test_wp_ohne_param_meldet_heizwaerme_warnung(db):
    """Legacy-WP ohne wp_art-Parameter zählt als klassische WP, bekommt Warnung."""
    anlage = Anlage(
        anlagenname="TestLegacy",
        leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Legacy WP", anschaffungsdatum=date(2025, 1, 1),
        parameter={},  # kein wp_art
    )
    db.add(wp)
    await db.flush()

    for monat in range(1, 6):
        db.add(_imd(wp.id, 2025, monat, stromverbrauch_kwh=100.0))
    for monat in range(1, 6):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=200.0, netzbezug_kwh=150.0,
        ))
    await db.commit()

    anlage_loaded, monatsdaten = await _reload_anlage(db, anlage.id)
    wp_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

    checker = DatenChecker(db)
    ergebnisse = checker._check_wp_monatsdaten(
        wp_loaded, "Legacy WP", wp_loaded.parameter, monatsdaten
    )

    heiz_warnungen = [
        e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
    ]
    assert heiz_warnungen, "Legacy-WP ohne wp_art darf nicht als Klima durchgehen"


# ============================================================================
# N-87 / #263 K-0b: Hinweise, die nur den Gas-Vergleich füttern, entfallen
# ============================================================================
#
# Seit N-87 rechnet das ROI-Dashboard einer Klimaanlage keine Ersparnis gegen
# eine Gasheizung mehr. Die drei Stammdaten-Hinweise, die ausschließlich diesen
# Vergleich versorgen, wären damit Forderungen ohne Zweck — und
# „Heizwärmebedarf" wäre sogar UNAUFLÖSBAR, weil das Formular das Feld für
# Klimaanlagen nicht mehr anbietet. Genau die Klasse, die P-6 abgeräumt hat.


async def _anlage_mit_wp(db, *, parameter: dict) -> tuple:
    anlage = Anlage(
        anlagenname="TestStammdaten", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Testgerät", anschaffungsdatum=date(2025, 1, 1),
        anschaffungskosten_gesamt=8000.0,
        parameter=parameter,
    ))
    await db.commit()
    return await _reload_anlage(db, anlage.id)


# Die drei Meldungen, die am Gas-Vergleich hängen.
#
# ⚠ **Die Gruppierung ist mit F-41 zerfallen (18.08.2026) und steht hier nur
# noch als Namensliste.** Bis dahin gingen alle drei aus EINEM Prädikat hervor —
# der Bauart — und diese Datei prüfte genau das. Beide Annahmen dahinter sind
# widerlegt:
#
# 1. Die zwei INFO hängen an der **Pflege** (`alter_energietraeger`), nicht an
#    der Bauart: Eine Klimaanlage, mit der jemand heizt, braucht sie; eine
#    Neubau-Luft-Wasser-WP nicht.
# 2. Die WARNING hängt an **keiner** der beiden Achsen — sie fragt nach der
#    vermiedenen *Investition* und gilt für jede Wärmepumpe.
#
# Die neuen Prüfer stehen in `test_f41_f42_klima_bewertbarkeit.py`. Was hier
# bleibt, ist die Hälfte, die **weiterhin an der Bauart hängt**: die
# Messbarkeit (Wärmemengenzähler) — siehe die Tests weiter unten.
GAS_VERGLEICHS_MELDUNGEN = (
    "Alternativkosten (Gas-/Ölheizung) fehlen",
    "Alter Energiepreis nicht gesetzt",
    "Heizwärmebedarf nicht gesetzt",
)


def _gas_meldungen(ergebnisse) -> list[str]:
    return [
        e.meldung for e in ergebnisse
        if any(m in e.meldung for m in GAS_VERGLEICHS_MELDUNGEN)
    ]


async def test_klima_die_bauart_unterdrueckt_die_hinweise_NICHT_mehr(db):
    """F-41: hieß bis 18.08.2026 `test_klima_bekommt_keine_gas_vergleichs_hinweise`.

    Die alte Behauptung war *„eine Klimaanlage kann diese Hinweise nicht
    auflösen"* — und sie war an zwei Stellen falsch. Die WARNING ist mit einer
    **0** auflösbar (die Prüfung ist `is None`), und die zwei INFO sind mit
    *„Nichts ersetzt (Neubau)"* auflösbar, seit es dieses Feld gibt (v4.0.18).
    Was blieb, war ein **Falsch-negativ**: Wer mit seiner Klimaanlage heizt,
    bekam keinen einzigen Hinweis auf die fehlenden Vergleichsgrößen, an denen
    seine Ersparnis hängt.

    Der Test steht bewusst mit umgekehrtem Vorzeichen weiter hier, statt gelöscht
    zu werden: Er ist die Stelle, an der die alte Regel gelebt hat, und die
    Umkehrung ist die sichtbare Folge, die im WAS-IST-NEU angekündigt ist.
    """
    anlage, monatsdaten = await _anlage_mit_wp(db, parameter={"wp_art": "luft_luft"})

    checker = DatenChecker(db)
    offen = _gas_meldungen(checker._check_investitionen(anlage, monatsdaten))

    for erwartet in GAS_VERGLEICHS_MELDUNGEN:
        assert any(erwartet in m for m in offen), (
            f"fehlt: {erwartet} — die Bauart darf nicht mehr unterdrücken"
        )


async def test_klassische_wp_bekommt_die_gas_vergleichs_hinweise_weiterhin(db):
    """Negativprobe: bei einer Luft-Wasser-WP feuern alle drei unverändert.

    Sie ist seit F-41 keine Abgrenzung gegen die Klimaanlage mehr, sondern die
    Absicherung, dass die Umstellung auf `alter_energietraeger` den Regelfall
    nicht stillgelegt hat.
    """
    anlage, monatsdaten = await _anlage_mit_wp(db, parameter={"wp_art": "luft_wasser"})

    checker = DatenChecker(db)
    ergebnisse = checker._check_investitionen(anlage, monatsdaten)

    offen = _gas_meldungen(ergebnisse)
    for erwartet in GAS_VERGLEICHS_MELDUNGEN:
        assert any(erwartet in m for m in offen), f"fehlt: {erwartet}"


# ─── N-86: dieselbe Unterscheidung auf der Zuordnungs-Fläche ─────────────────
#
# Der Daten-Checker schweigt seit K-0 zur fehlenden Heizwärme (die Tests oben).
# *Einstellungen → Datenquellen* und die MQTT-Topic-Liste taten das Gegenteil:
# sie zeigten „Heizwärme" rot, aufgeklappt und zählten sie als offene Pflicht.
# Beide lesen ihre Einstufung aus `build_expected_topics`, deshalb wird hier
# die Fläche geprüft und nicht nur `get_feld_bedarf` — der Weg von der Tabelle
# bis zum Response-Feld ist der Teil, der vorher gefehlt hat.

async def _bedarf_je_feld(db, *, parameter: dict) -> dict[str, str]:
    """{feldname: bedarf} der Investitions-Einträge aus der Topic-Registry."""
    from backend.services.mqtt_topic_registry import build_expected_topics

    anlage, _ = await _anlage_mit_wp(db, parameter=parameter)
    eintraege = await build_expected_topics(db, anlage, investitionen=anlage.investitionen)
    return {
        e["feld"]: e["bedarf"] for e in eintraege
        if e["match_key"][0] in ("inv_energy", "inv_live")
    }


async def test_klima_fordert_die_heizwaerme_nicht_als_pflicht(db):
    """Klimaanlage: „Heizwärme" ist auf der Zuordnungs-Fläche optional."""
    bedarf = await _bedarf_je_feld(db, parameter={"wp_art": "luft_luft"})

    assert bedarf["heizenergie_kwh"] == "optional", (
        "Eine Split-Klimaanlage hat keinen Wärmemengenzähler — die Fläche darf "
        "dort keine Pflicht ausweisen, während der Daten-Checker dazu schweigt"
    )
    # Der Strom bleibt Pflicht: K-0b entfernt die Wärme-Erwartung, nicht das Gerät.
    assert bedarf["stromverbrauch_kwh"] == "pflicht"


async def test_klassische_wp_fordert_die_heizwaerme_weiterhin(db):
    """Negativprobe: bei Luft-Wasser bleibt die Heizwärme Pflicht.

    Ohne sie wäre die Ausnahme oben nicht von „heizenergie_kwh ist jetzt
    überall optional" zu unterscheiden.
    """
    bedarf = await _bedarf_je_feld(db, parameter={"wp_art": "luft_wasser"})

    assert bedarf["heizenergie_kwh"] == "pflicht"


async def test_wp_ohne_wp_art_bleibt_klassisch(db):
    """Altbestand ohne `wp_art` zählt als klassische WP — wie der SoT-Helper.

    Eine fehlende Angabe darf die Wärmemengen-Erwartung nicht stillschweigend
    abschalten (Begründung im Docstring von `ist_luft_luft_waermepumpe`).
    """
    bedarf = await _bedarf_je_feld(db, parameter={})

    assert bedarf["heizenergie_kwh"] == "pflicht"
