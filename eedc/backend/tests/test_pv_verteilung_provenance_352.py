"""Ein gerechneter Wert behauptet keine Messung (#352).

Bis v4.0.8 landete eine kWp-Zerlegung als gewöhnlicher Pro-Modul-Wert in
``InvestitionMonatsdaten.verbrauch_daten`` — ununterscheidbar von einer
Gerätemessung. Die Lesezeit klassifizierte ihn deshalb als ``gemessen``, mit
zwei sichtbaren Folgen: das String-Ranking verglich Zahlen, die per
Konstruktion proportional zur kWp sind, und der Daten-Checker meldete OK für
einen Monat, in dem kein einziger String gemessen hat.

Der Weg (Entscheide Gernot 2026-08-05): die Herkunft steht als ``abgeleitet``
im ``source_provenance``-Eintrag **derselben Zeile** — keine eigene
Source-Stufe (das wäre die bei N-102 verneinte Stufenfrage), kein neues
Datenfeld, keine Log-Abfrage zur Lesezeit.

Der Wert selbst wird nie verändert: er steht so in der DB und bleibt stehen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.pv_verteilung import (
    QUELLE_GEMESSEN,
    QUELLE_VERTEILT,
    STATUS_OK,
    STATUS_VERTEILT,
    PvModul,
    klassifiziere_pv_monat,
    resolve_pv_je_modul,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.daten_checker import CheckSeverity, DatenChecker
from backend.services.provenance import (
    ABGELEITET_KAPAZITAET_ANTEIL,
    ABGELEITET_KWP_ANTEIL,
    gepruefte_ableitung,
    gepruefte_ableitungen,
)
from backend.services.pv_monatswerte import lade_pv_je_monat


# ── Formel-Ebene ─────────────────────────────────────────────────────────────

def test_abgeleiteter_wert_ist_verteilt_nicht_gemessen():
    """Die Zahl bleibt, das Etikett wechselt."""
    module = [
        PvModul(inv_id=1, leistung_kwp=6.0, eigen_kwh=600.0, eigen_ist_abgeleitet=True),
        PvModul(inv_id=2, leistung_kwp=4.0, eigen_kwh=400.0, eigen_ist_abgeleitet=True),
    ]
    out = resolve_pv_je_modul(aggregat_kwh=None, module=module)
    assert out[1].pv_erzeugung_kwh == 600.0
    assert out[2].pv_erzeugung_kwh == 400.0
    assert out[1].quelle == QUELLE_VERTEILT
    assert out[2].quelle == QUELLE_VERTEILT


def test_gemischt_nur_der_abgeleitete_wechselt():
    """Ein echter Messwert neben einer Zerlegung bleibt gemessen."""
    module = [
        PvModul(inv_id=1, leistung_kwp=6.0, eigen_kwh=610.0),
        PvModul(inv_id=2, leistung_kwp=4.0, eigen_kwh=390.0, eigen_ist_abgeleitet=True),
    ]
    out = resolve_pv_je_modul(aggregat_kwh=None, module=module)
    assert out[1].quelle == QUELLE_GEMESSEN
    assert out[2].quelle == QUELLE_VERTEILT


def test_ohne_markierung_bleibt_alles_wie_bisher():
    """Gegenprobe: der Default ändert nichts (Altbestand ist ambig, nicht falsch)."""
    module = [PvModul(inv_id=1, leistung_kwp=6.0, eigen_kwh=600.0)]
    assert resolve_pv_je_modul(aggregat_kwh=None, module=module)[1].quelle == QUELLE_GEMESSEN


def test_klassifikation_abgeleitet_ohne_aggregat_ist_verteilt_nicht_fehlt():
    """Der Randfall, an dem die Markierung sonst zur Verschlechterung würde.

    Ein vollständig importierter Monat hat Werte in jeder Zeile, aber keine
    Messung — ohne diesen Zweig meldete der Checker ERROR („gar keine
    PV-Quelle"), obwohl die Zahlen da sind.
    """
    assert klassifiziere_pv_monat(
        n_aktive_module=2, n_gemessen=0, aggregat_kwh=None, n_abgeleitet=2,
    ) == STATUS_VERTEILT
    # Gegenprobe: gemessen bleibt OK
    assert klassifiziere_pv_monat(
        n_aktive_module=2, n_gemessen=2, aggregat_kwh=None,
    ) == STATUS_OK


# ── Positivliste ─────────────────────────────────────────────────────────────

def test_unbekannte_marke_wird_verworfen():
    """Was die Lesezeit nicht auswerten kann, darf nicht in die Provenance."""
    assert gepruefte_ableitung(ABGELEITET_KWP_ANTEIL) == ABGELEITET_KWP_ANTEIL
    assert gepruefte_ableitung("gemessen_ehrenwort") is None
    assert gepruefte_ableitung(None) is None
    assert gepruefte_ableitung(17) is None


def test_feldweise_pruefung_filtert_einzeln():
    out = gepruefte_ableitungen({
        "pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL,
        "ladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
        "km_gefahren": "phantasie",
    })
    assert out == {
        "pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL,
        "ladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
    }
    assert gepruefte_ableitungen(None) == {}


# ── Ladepfad: die Markierung kommt aus derselben Zeile ────────────────────────

async def _seed_zwei_strings(db, *, provenance_sued=None, aggregat=None) -> Anlage:
    anlage = Anlage(anlagenname="PV-352", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       pv_erzeugung_kwh=aggregat))
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0)
    db.add_all([sued, ost])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=sued.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 600.0},
        source_provenance=provenance_sued or {},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ost.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 400.0},
        source_provenance=provenance_sued or {},
    ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(
            selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
            selectinload(Anlage.monatsdaten),
        )
        .where(Anlage.id == anlage.id)
    )).scalar_one()


_PROV_ABGELEITET = {
    "verbrauch_daten.pv_erzeugung_kwh": {
        "source": "manual:csv_backup",
        "writer": "csv_backup_restore",
        "at": "2026-08-05T00:00:00Z",
        "abgeleitet": ABGELEITET_KWP_ANTEIL,
    }
}


async def test_ladepfad_liest_die_markierung_aus_der_zeile(db):
    anlage = await _seed_zwei_strings(db, provenance_sued=_PROV_ABGELEITET)
    module = [i for i in anlage.investitionen if i.typ == "pv-module"]
    monate = await lade_pv_je_monat(db, anlage.id, module)
    werte = monate[(2026, 5)]
    assert {w.quelle for w in werte.values()} == {QUELLE_VERTEILT}
    # Die Zahlen sind unangetastet — es geht um die Herkunft, nicht den Wert.
    assert sorted(w.pv_erzeugung_kwh for w in werte.values()) == [400.0, 600.0]


async def test_ladepfad_ohne_markierung_bleibt_gemessen(db):
    """Gegenprobe gegen den Altbestand: ohne Marke ändert sich nichts."""
    anlage = await _seed_zwei_strings(db)
    module = [i for i in anlage.investitionen if i.typ == "pv-module"]
    monate = await lade_pv_je_monat(db, anlage.id, module)
    assert {w.quelle for w in monate[(2026, 5)].values()} == {QUELLE_GEMESSEN}


async def test_daten_checker_meldet_info_statt_ok(db):
    """Ein Monat ohne eine einzige Messung ist nicht grün."""
    anlage = await _seed_zwei_strings(db, provenance_sued=_PROV_ABGELEITET)
    checker = DatenChecker(db)
    res = checker._check_pv_erzeugung(anlage, list(anlage.monatsdaten))
    assert res, "Der Checker muss den Monat benennen"
    assert not any(r.schwere == CheckSeverity.OK for r in res), res
    # Auf den Zustand prüfen, nicht auf den Meldungs-Wortlaut: der Monat muss
    # in einem INFO-Befund auftauchen (die INFO-Stufe ist der Kanon für
    # „über kWp-Anteil geschätzt"). Ein Text-Feinschliff darf diesen Test
    # nicht stumm machen ([[feedback_wortlaut_filter_macht_tests_stumm]]).
    assert any(
        r.schwere == CheckSeverity.INFO and "05/2026" in (r.details or "")
        for r in res
    ), res
