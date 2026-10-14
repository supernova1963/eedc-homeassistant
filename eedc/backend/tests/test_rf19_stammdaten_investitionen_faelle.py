"""RF-19 — drei Meldungen des Investitions-Checks, die weder die übrige Suite noch die Golden-Master-Bestände erreichen.

Der Schnitt von ``_check_investitionen`` (RF-19, Serie „Funktion vor Datei", 14.10.2026) ist ein reiner Umzug: der Orchestrator
bleibt in ``services/daten_checker/stammdaten.py``, je Investitionstyp eine Phase steht im Schwestermodul
``stammdaten_investitionen.py``. Die Vorlage (§0, Linienspur über die 35 Aufruferdateien) hat gemessen, dass drei Zweige sonst
von keinem Test ausgeführt werden; dort war die Fall-Probe das einzige Gate (Sprengsätze S12–S14 und S21 der Vorlage):

* **F1** — Netzladung übersteigt Gesamtladung, **kumulativ** über die Historie (#281); ein einzelner Monat darf das.
* **F2** — Entladung übersteigt Ladung, **kumulativ** (F-22, N-252/N-264), (a) mit Netzladung samt Hinweis auf die GESAMTE
  Ladung, (b) ohne Netzladung ohne diesen Hinweis; ohne Ladung kein Wirkungsgrad, keine Meldung (c).
* **F3** — JAZ außerhalb 1,5–7,0 ist unplausibel (Modus «gesamt_jaz»).

Schwesterdateien: test_f22_speicher_wirkungsgrad_kanon.py (F-22, Quelltext-Probe auf dieselbe Meldung),
test_n252_speicher_wirkungsgrad_deckung.py (der ungekappte Wirkungsgrad-Helper im Diagnose-Verwender),
test_berechnungen_invarianten.py (``pruefe_speicher_netzladung_kumulativ`` selbst), test_f41_f42_klima_bewertbarkeit.py
(Wärmepumpen-Zweig des Checkers), test_rf18_finanz_prognose_faelle.py (dieselbe Fall-Probe für die Finanz-Prognose).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity

_MONATSDATEN_LINK = "/einstellungen/daten?block=monatsdaten"


async def _anlage_mit(db, typ: str, parameter: dict, daten_je_monat: dict[int, dict] | None = None) -> Anlage:
    anlage = Anlage(anlagenname="RF-19", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="G", anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0, anschaffungskosten_alternativ=500.0, parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    for monat, daten in (daten_je_monat or {}).items():
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2025, monat=monat, verbrauch_daten=daten))
    await db.commit()
    # `monatsdaten` mitladen: die Speicher-Phase faltet sie kumulativ (wie `check_anlage`).
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


def _treffer(ergebnisse, meldung: str):
    return [r for r in ergebnisse if r.meldung == meldung]


async def test_f1_netzladung_ueber_gesamtladung_kumulativ(db):
    # Monat 1: Netz 60 > Gesamt 50 (Schnappschuss an der Monatsgrenze, für sich erlaubt); Monat 2 gleicht nicht aus.
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10, "laedt_aus_netz": True}, {
        1: {"ladung_kwh": 50.0, "ladung_netz_kwh": 60.0, "entladung_kwh": 45.0},
        2: {"ladung_kwh": 50.0, "ladung_netz_kwh": 90.0, "entladung_kwh": 45.0},
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    treffer = _treffer(erg, "G (speicher): Netzladung übersteigt Gesamtladung (kumulativ)")
    assert len(treffer) == 1, [r.meldung for r in erg]
    t = treffer[0]
    assert (t.kategorie, t.schwere, t.link) == (CheckKategorie.INVESTITIONEN, CheckSeverity.WARNING, _MONATSDATEN_LINK)
    assert t.details.startswith("Kumulierte Netzladung (") and t.details.endswith("(Issue #281).")
    assert t.investition_id == anlage.investitionen[0].id
    assert not [r for r in erg if "Entladung übersteigt Ladung" in r.meldung]


async def test_f1_details_schreiben_deutsche_zahlen(db):
    """Die Details-Zeile nennt die beiden Summen deutsch, ganzzahlig wie die Schwester-Meldung (Entladung > Ladung).

    Bis 14.10.2026 stand hier «1500.000 kWh» — nach deutscher Lesart anderthalb Millionen. Der Text entsteht in
    ``core/berechnungen/invarianten.py`` und wird vom Checker nur durchgereicht.
    """
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10, "laedt_aus_netz": True}, {
        1: {"ladung_kwh": 600.0, "ladung_netz_kwh": 750.0, "entladung_kwh": 540.0},
        2: {"ladung_kwh": 600.0, "ladung_netz_kwh": 750.0, "entladung_kwh": 540.0},
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    (t,) = _treffer(erg, "G (speicher): Netzladung übersteigt Gesamtladung (kumulativ)")
    assert t.details.startswith(
        "Kumulierte Netzladung (1.500 kWh) übersteigt die kumulierte Gesamtladung (1.200 kWh) — "
    ), t.details
    assert "1500.000" not in t.details and "1200.000" not in t.details, t.details


async def test_f1_netzladung_innerhalb_der_gesamtladung_schweigt(db):
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10, "laedt_aus_netz": True}, {
        1: {"ladung_kwh": 50.0, "ladung_netz_kwh": 60.0, "entladung_kwh": 45.0},
        2: {"ladung_kwh": 50.0, "ladung_netz_kwh": 30.0, "entladung_kwh": 45.0},
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    assert not [r for r in erg if "Netzladung übersteigt" in r.meldung], [r.meldung for r in erg]


async def test_f2a_entladung_ueber_ladung_mit_netzladung(db):
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10, "laedt_aus_netz": True}, {
        8: {"ladung_kwh": 100.0, "ladung_netz_kwh": 30.0, "entladung_kwh": 130.0},
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    treffer = _treffer(erg, "G (speicher): Entladung übersteigt Ladung (kumulativ)")
    assert len(treffer) == 1, [r.meldung for r in erg]
    t = treffer[0]
    assert (t.kategorie, t.schwere, t.link) == (CheckKategorie.INVESTITIONEN, CheckSeverity.WARNING, _MONATSDATEN_LINK)
    assert t.details == (
        "Über die gesamte Historie stehen 130 kWh Entladung gegen 100 kWh Ladung (130 %). "
        "Ein Speicher kann nicht mehr abgeben, als er aufgenommen hat. "
        "Häufigste Ursache: „Ladung“ enthält nur die PV-Ladung. Dort gehört die GESAMTE Ladung hinein — "
        "die Netzladung ist ein Teil davon, kein zweiter Posten daneben."
    )
    assert t.investition_id == anlage.investitionen[0].id


async def test_f2b_entladung_ueber_ladung_ohne_netzladung_summiert_alle_monate(db):
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10}, {
        8: {"ladung_kwh": 60.0, "entladung_kwh": 1000.0},
        9: {"ladung_kwh": 40.0, "entladung_kwh": 234.5},
        10: {"ladung_kwh": None, "entladung_kwh": None},
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    treffer = _treffer(erg, "G (speicher): Entladung übersteigt Ladung (kumulativ)")
    assert len(treffer) == 1, [r.meldung for r in erg]
    assert treffer[0].details == (
        "Über die gesamte Historie stehen 1.234 kWh Entladung gegen 100 kWh Ladung (1.234 %). "
        "Ein Speicher kann nicht mehr abgeben, als er aufgenommen hat."
    )


async def test_f2c_ohne_ladung_kein_wirkungsgrad_und_keine_meldung(db):
    anlage = await _anlage_mit(db, "speicher", {"kapazitaet_kwh": 10}, {8: {"entladung_kwh": 50.0}})
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    assert not [r for r in erg if "kumulativ" in r.meldung], [r.meldung for r in erg]


async def test_f3_jaz_unplausibel(db):
    anlage = await _anlage_mit(db, "waermepumpe", {
        "effizienz_modus": "gesamt_jaz", "jaz": 8.25, "alter_preis_cent_kwh": 12.0, "heizwaermebedarf_kwh": 9000,
        "warmwasserbedarf_kwh": 1500, "alter_energietraeger": "gas",
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    treffer = _treffer(erg, "G (waermepumpe): JAZ unplausibel (8,2)")
    assert len(treffer) == 1, [r.meldung for r in erg]
    t = treffer[0]
    assert (t.kategorie, t.schwere, t.link) == (
        CheckKategorie.INVESTITIONEN, CheckSeverity.WARNING, "/einstellungen/investitionen",
    )
    assert t.details == "Typischer Bereich: 1,5–7,0 (Luft-WP ca. 2,5–4,5, Sole-WP ca. 3,5–5,5)"
    assert t.investition_id == anlage.investitionen[0].id
    assert not [r for r in erg if "JAZ fehlt" in r.meldung]


async def test_f3_jaz_im_bereich_schweigt(db):
    anlage = await _anlage_mit(db, "waermepumpe", {
        "effizienz_modus": "gesamt_jaz", "jaz": 7.0, "alter_preis_cent_kwh": 12.0, "heizwaermebedarf_kwh": 9000,
        "warmwasserbedarf_kwh": 1500, "alter_energietraeger": "gas",
    })
    erg = DatenChecker(db)._check_investitionen(anlage, [])
    assert not [r for r in erg if "JAZ" in r.meldung], [r.meldung for r in erg]
