"""N-751 (16.10.2026), Daten-Checker: Prüfung 0 («Netzfeld nicht erfasst», N-734) auch für Monate OHNE Monatszeile mit
Tageswerten — ERROR je Feld, mit Rat; keine Doppelmeldung für Monate mit Zeile. Fixture wie
``test_n751_monat_ohne_zeile_netzfeld_nicht_erfasst.py`` (Juli 2026 nur Tagesebene)."""

from __future__ import annotations

from backend.models import Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie
from backend.tests.test_n751_monat_ohne_zeile_netzfeld_nicht_erfasst import _juli_nur_tage


async def _pruefung0(db, aid) -> list[str]:
    erg = await DatenChecker(db).check_anlage(aid)
    return [e.meldung for e in erg.ergebnisse
            if getattr(e.kategorie, "value", e.kategorie) == CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value
            and "nicht erfasst" in e.meldung]


async def test_ohne_einspeisungs_sensor_meldet_den_monat(db):
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    assert await _pruefung0(db, a.id) == ["07/2026: Einspeisung nicht erfasst (Monat ohne Monatsabschluss)"]


async def test_ohne_netz_sensoren_je_feld_eine_meldung(db):
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=False)
    assert await _pruefung0(db, a.id) == ["07/2026: Einspeisung nicht erfasst (Monat ohne Monatsabschluss)",
                                          "07/2026: Netzbezug nicht erfasst (Monat ohne Monatsabschluss)"]


async def test_erfasst_meldet_nichts(db):
    a = await _juli_nur_tage(db, einspeisung=True, netzbezug=True)
    assert await _pruefung0(db, a.id) == []


async def test_monat_mit_zeile_nur_die_bestehende_pruefung(db):
    """Keine Doppelmeldung: mit Zeile (Einspeisung 0 ohne Herkunft) meldet nur Prüfung 0 der Zeile."""
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=7, netzbezug_kwh=3.0,
                       source_provenance={"netzbezug_kwh": {"source": "manual:form"}}))
    await db.commit()
    assert await _pruefung0(db, a.id) == ["07/2026: Einspeisung nicht erfasst"]


async def _stub_monat(db, *, stunden: int):
    """Monat ohne Zeile mit EINER Tageszeile ohne Werte — wie der Stub, den ein Monatsabschluss des laufenden Monats für
    Zukunftstage anlegt (gemessen 09/2026 auf den Mess-Kopien: ``stunden_verfuegbar = 0``, ``komponenten_kwh`` leer)."""
    from datetime import date

    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.tests import factories

    a = await factories.anlage(db, anlagenname="Stub", standort_land="DE")
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 9, 29), stunden_verfuegbar=stunden,
                                pv_prognose_kwh=12.0))
    await db.commit()
    return a


async def test_stub_monat_ohne_echte_tage_meldet_nichts(db):
    """Entscheid Master 16.10.: ein Monat zählt nur mit echten Tagen (Stunden oder ein erfasstes Bilanz-Feld)."""
    a = await _stub_monat(db, stunden=0)
    assert await _pruefung0(db, a.id) == []


async def test_tage_mit_stunden_ohne_bilanz_feld_werden_gemeldet(db):
    """Gegenprobe zur Stub-Regel: trägt die Tageszeile Stunden, ist der Monat echt — ohne jedes Netzfeld beide Meldungen."""
    a = await _stub_monat(db, stunden=24)
    assert await _pruefung0(db, a.id) == ["09/2026: Einspeisung nicht erfasst (Monat ohne Monatsabschluss)",
                                          "09/2026: Netzbezug nicht erfasst (Monat ohne Monatsabschluss)"]


async def test_rat_nennt_datenquelle_und_monatsabschluss(db):
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    erg = await DatenChecker(db).check_anlage(a.id)
    e = next(e for e in erg.ergebnisse if e.meldung.startswith("07/2026: Einspeisung nicht erfasst"))
    assert "Datenquelle zuordnen (Einstellungen → Datenquellen" in e.details
    assert "den Monat im Monatsabschluss pflegen" in e.details
    assert "Cockpit → Monat und Cockpit → Jahr" in e.details
    assert e.link and "2026-07" in e.link


async def test_n734_text_mit_zeile_meint_monat_und_jahr(db):
    """N-734-Wortlaut (Monat mit Zeile): «sonst bleiben … leer» gilt für Cockpit → Monat UND → Jahr (Monatsliste, N-736)."""
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=7, netzbezug_kwh=3.0,
                       source_provenance={"netzbezug_kwh": {"source": "manual:form"}}))
    await db.commit()
    erg = await DatenChecker(db).check_anlage(a.id)
    e = next(e for e in erg.ergebnisse if e.meldung == "07/2026: Einspeisung nicht erfasst")
    assert "sonst bleiben Eigenverbrauch und Autarkie des Monats in Cockpit → Monat und Cockpit → Jahr leer" in e.details


async def test_keine_doppelmeldung_wenn_die_tagesebene_die_zeile_ergaenzt(db):
    """Zeile mit beiden Netzfeldern ohne Herkunft (0,0), Tagesebene erfasst den Netzbezug (N-736 füllt ihn, Marke
    ``zaehler``): gemeldet wird nur Prüfung 0 der Zeile — nicht zusätzlich die Fassung «ohne Monatsabschluss»."""
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=7))
    await db.commit()
    assert await _pruefung0(db, a.id) == ["07/2026: Einspeisung nicht erfasst", "07/2026: Netzbezug nicht erfasst"]
