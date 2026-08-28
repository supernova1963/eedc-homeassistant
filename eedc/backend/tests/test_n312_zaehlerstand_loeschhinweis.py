"""N-312: Vor dem Löschen wird gesagt, was ein Zählerstand ist.

**Der Befund.** Der Daten-Checker meldet Gerätewerte, deren Monatszeile fehlt,
und stellt einen Knopf „Messwerte entfernen" daneben. Der Text darunter lautete
für **jede** Datenart gleich: *„Nur wenn sie gar nicht mehr gebraucht werden,
entferne sie."* Für einen **Zählerstand** sagt dieser Satz das Gegenteil.

**Warum.** Ein Zählerstand ist eine Bestandsgröße; die einzige Rechnung darauf
ist Ende − Anfang, und den Anfang holt ``zaehlerstaende.lade_zaehlerstaende``
als letzten Stand **vor** dem Fenster (``davor[-1]``). Fällt der Stand des
Monats M weg, greift das Fenster M+1 auf M−1 zurück und weist **zwei Monate als
einen** aus — mit ``anfang_vollstaendig=True``, also ohne jede Warnung.
Gebraucht wird der Stand nicht von seinem Monat, sondern vom nächsten.

⛔ **Gesagt, nicht verboten.** Der Knopf bleibt; eedc entscheidet nicht für den
Anwender, wann ein Stand entbehrlich ist
([[feedback_eedc_ist_nicht_die_strom_polizei]]).

Die Klasse saß an **zwei** Stellen — dem Daten-Checker-Weg (hier) und dem
regulären Lösch-Dialog, der über ``beschreibe_geraetewerte_des_monats`` je
Komponente ``ist_zaehler`` bekommt (zweiter Testblock).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.core.field_definitions import ZAEHLERSTAND_FELD
from backend.core.investition_parameter import PARAM_SONSTIGES
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.daten_checker import DatenChecker, CheckKategorie
from backend.services.monat_loeschen import beschreibe_geraetewerte_des_monats

_KAT = CheckKategorie.GERAETEWERTE_OHNE_MONATSZEILE


def _imd(jahr, monat, **felder):
    return SimpleNamespace(jahr=jahr, monat=monat, verbrauch_daten=dict(felder))


def _zaehler_inv(inv_id=11, bezeichnung="Gaszähler"):
    return SimpleNamespace(
        id=inv_id, typ="sonstiges", bezeichnung=bezeichnung,
        parameter={PARAM_SONSTIGES["KATEGORIE"]: "zaehler"},
        monatsdaten=[_imd(2026, 6, **{ZAEHLERSTAND_FELD: 12345.0})],
    )


def _pv_inv(inv_id=3, bezeichnung="Dach Süd"):
    return SimpleNamespace(
        id=inv_id, typ="pv-module", bezeichnung=bezeichnung, parameter={},
        monatsdaten=[_imd(2026, 6, pv_erzeugung_kwh=420.0)],
    )


def _run(investitionen):
    anlage = SimpleNamespace(id=1, investitionen=investitionen)
    return DatenChecker(MagicMock())._check_geraetewerte_ohne_monatszeile(anlage, [])


def test_zaehlerstand_bekommt_den_hinweis_auf_den_folgemonat():
    ergebnisse = _run([_zaehler_inv()])
    assert len(ergebnisse) == 1, ergebnisse
    e = ergebnisse[0]
    assert e.kategorie == _KAT
    assert "Gaszähler" in e.details
    assert "Anfangsstand des Folgemonats" in e.details, e.details
    assert "zwei Monate als einen" in e.details, e.details
    # Der Knopf bleibt — gesagt, nicht verboten.
    assert e.action_kind == "geraetewerte_loeschen"
    assert e.action_params["hat_zaehler"] is True


def test_ohne_zaehler_bleibt_der_text_wie_er_war():
    """Gegenrichtung: Bei einer Menge ist ein gelöschter Monat genau das —
    dieser Monat fehlt. Der Zusatz darf dort nicht stehen, sonst verlernt der
    Anwender ihn."""
    ergebnisse = _run([_pv_inv()])
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert "Anfangsstand des Folgemonats" not in e.details
    assert "Zählerstände" not in e.details
    assert e.action_params["hat_zaehler"] is False


def test_gemischter_monat_nennt_nur_die_zaehler_beim_namen():
    """Hängen beide Arten am selben Monat, muss der Zusatz sagen, WELCHE
    Geräte er meint — sonst liest sich der Rat, als gälte er für die PV mit."""
    ergebnisse = _run([_pv_inv(), _zaehler_inv()])
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.action_params["hat_zaehler"] is True
    hinweis = e.details.split("Achtung:")[1]
    assert "Gaszähler" in hinweis
    assert "Dach Süd" not in hinweis, hinweis
    # Der allgemeine Teil nennt weiterhin beide.
    assert "Dach Süd" in e.details.split("Achtung:")[0]


@pytest.mark.asyncio
async def test_beschreibung_traegt_die_datenart_fuer_den_loesch_dialog(db):
    """Der zweite Ort derselben Klasse: der reguläre „Monat löschen"-Dialog.

    Er nennt die Komponenten längst beim Namen — aber nicht ihre Datenart. Ohne
    `ist_zaehler` kann er den Satz über den Folgemonat nicht setzen.
    """
    anlage_id = 1
    md = Monatsdaten(anlage_id=anlage_id, jahr=2026, monat=6,
                     einspeisung_kwh=100.0, netzbezug_kwh=200.0)
    gas = Investition(
        anlage_id=anlage_id, typ="sonstiges", bezeichnung="Gaszähler",
        anschaffungsdatum=None,
        parameter={PARAM_SONSTIGES["KATEGORIE"]: "zaehler"},
    )
    pv = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=None, parameter={},
    )
    db.add_all([md, gas, pv])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=gas.id, jahr=2026, monat=6,
                               verbrauch_daten={ZAEHLERSTAND_FELD: 12345.0}),
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                               verbrauch_daten={"pv_erzeugung_kwh": 420.0}),
    ])
    await db.flush()

    beschreibung = await beschreibe_geraetewerte_des_monats(
        db, anlage_id, 2026, 6,
    )
    je_name = {b["bezeichnung"]: b for b in beschreibung}
    assert je_name["Gaszähler"]["ist_zaehler"] is True
    assert je_name["Dach Süd"]["ist_zaehler"] is False
