"""Konzept §9 Weg 2 (Bauschritt 9) — Erlös je Erzeuger mit eigenem Tarif.

eedc kennt genau **einen** Einspeisesatz je Anlage (``Strompreis.anlage_id``).
Wer einen zweiten Erzeuger mit eigenem Vergütungssatz betreibt (#310,
rilmor-mhrs), konnte dessen Erlös deshalb nur Monat für Monat von Hand buchen.
Das neue Feld ``einspeise_erloes_euro`` an *Sonstiges/Erzeuger* nimmt ihn als
**gemessenen Monatswert** entgegen — befüllbar aus einem HA-Helfer.

⚠ **Kein Abzug von der Anlagen-Bewertung** (Entscheid Maintainer, 2026-08-10):
zwei Vergütungssätze bedeuten zwei Messungen, sonst könnte der Netzbetreiber
nicht abrechnen. In den Anlagen-Einspeisezähler gehört ohnehin nur die zum
Anlagentarif vergütete Menge — der Betrag kommt **zusätzlich** dazu.

Gesichert wird die ganze Kette, nicht nur der Layer: Feld → IMD-Aggregat →
Monats-Fakten → Finanz-Aggregat → **alle vier Sichten**. Genau daran ist #310
dreimal gescheitert: der Fix saß je in einer Sicht, die anderen rechneten
weiter ohne.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

ERLOES_JE_MONAT = 25.0
MONATE = 12


async def _anlage(db, *, erloes: float = 0.0, kategorie: str = "erzeuger",
                 name: str = "Zweittarif") -> int:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for monat in range(1, MONATE + 1):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=300.0, netzbezug_kwh=100.0))

    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Zweiter Erzeuger",
        anschaffungsdatum=date(2024, 12, 1), anschaffungskosten_gesamt=5000.0,
        parameter={"kategorie": kategorie},
    )
    db.add(inv)
    await db.flush()
    for monat in range(1, MONATE + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "erzeugung_kwh": 200.0,
                "einspeisung_kwh": 150.0,
                "einspeise_erloes_euro": erloes,
            },
        ))
    await db.commit()
    return anlage.id


def _sensor(sensoren, key: str):
    return next((s.value for s in sensoren if s.definition.key == key), None)


async def test_feld_ist_in_der_registry_und_traegt_die_einheit():
    """Ohne Registry-Eintrag erreicht ein Feld **keinen** automatischen Kanal —
    weder Monatsabschluss noch CSV, MQTT oder Datenquellen-Zuordnung
    ([[feedback_neue_felder_pflicht]])."""
    from backend.core.field_definitions import get_felder_fuer_sonstiges

    felder = {f["feld"]: f for f in get_felder_fuer_sonstiges("erzeuger")}
    assert "einspeise_erloes_euro" in felder
    assert felder["einspeise_erloes_euro"]["einheit"] == "€"
    # Der Verbraucher hat ihn nicht — er speist nicht ein.
    assert "einspeise_erloes_euro" not in {
        f["feld"] for f in get_felder_fuer_sonstiges("verbraucher")
    }


async def test_erloes_erreicht_alle_vier_sichten(db):
    """#310s eigentliche Lehre: eine Zahl, die nur eine Sicht kennt, ist ein Bug.

    Geprüft wird die **Differenz** zweier identischer Anlagen — die eine mit,
    die andere ohne gepflegten Erlös. Alles andere ist gleich, also muss der
    Unterschied genau Σ Erlös sein.
    """
    erwartet = ERLOES_JE_MONAT * MONATE

    mit = await _anlage(db, erloes=ERLOES_JE_MONAT, name="mit")
    ohne = await _anlage(db, erloes=0.0, name="ohne")

    # 1 · Aussichten (Zeitraum-Bilanz + Amortisations-Fortschritt)
    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    assert p_mit.bisherige_ertraege_euro - p_ohne.bisherige_ertraege_euro == pytest.approx(
        erwartet, abs=0.02
    )

    # 2 · HA-Sensor `netto_ertrag_euro` (Zeitraum-Bilanz)
    a_mit = (await db.execute(select(Anlage).where(Anlage.id == mit))).scalar_one()
    a_ohne = (await db.execute(select(Anlage).where(Anlage.id == ohne))).scalar_one()
    s_mit = await calculate_anlage_sensors(db, a_mit)
    s_ohne = await calculate_anlage_sensors(db, a_ohne)
    assert _sensor(s_mit, "netto_ertrag_euro") - _sensor(s_ohne, "netto_ertrag_euro") == (
        pytest.approx(erwartet, abs=0.02)
    )

    # 3 · Cockpit → Jahr. ⚠ Diese Sicht baut ihren Netto-Ertrag aus den
    # Einzel-Komponenten selbst zusammen (USt-Abzug dazwischen) — sie war
    # deshalb die Stelle, an der #326 zuerst auseinanderlief.
    c_mit = await get_cockpit_uebersicht(anlage_id=mit, jahr=2025, db=db)
    c_ohne = await get_cockpit_uebersicht(anlage_id=ohne, jahr=2025, db=db)
    assert c_mit.netto_ertrag_euro - c_ohne.netto_ertrag_euro == pytest.approx(
        erwartet, abs=0.02
    )


async def test_erloes_mindert_nicht_den_anlagen_einspeiseerloes(db):
    """Der Betrag kommt **zusätzlich** — kein Gegenrechnen (Entscheid 2026-08-10).

    Zwei Vergütungssätze bedeuten zwei Messungen; im Anlagenzähler steht nur
    die zum Anlagentarif vergütete Menge. Würde eedc die Einspeisung dieses
    Erzeugers abziehen, verlöre der Anwender genau den Teil, den er korrekt
    erfasst hat.
    """
    mit = await _anlage(db, erloes=ERLOES_JE_MONAT, name="mit")
    ohne = await _anlage(db, erloes=0.0, name="ohne")

    a_mit = (await db.execute(select(Anlage).where(Anlage.id == mit))).scalar_one()
    a_ohne = (await db.execute(select(Anlage).where(Anlage.id == ohne))).scalar_one()

    einsp_mit = _sensor(await calculate_anlage_sensors(db, a_mit), "einspeise_erloes_euro")
    einsp_ohne = _sensor(await calculate_anlage_sensors(db, a_ohne), "einspeise_erloes_euro")
    # ⚠ Erst prüfen, ob die Probe überhaupt auf etwas zeigt: eine
    # Gleichheits-Assertion ist auch bei zwei ``None`` erfüllt (N-221-Klasse).
    assert einsp_mit and einsp_mit > 0, "kein Anlagen-Einspeiseerlös — Fixture defekt"
    assert einsp_mit == pytest.approx(einsp_ohne), (
        "der Anlagen-Einspeiseerlös darf sich durch einen gepflegten "
        "Erzeuger-Erlös NICHT ändern"
    )


async def test_verbraucher_traegt_keinen_einspeise_erloes(db):
    """Kategorie-Regel wie bei Eigenverbrauch/Einspeisung (C1d).

    Ein Verbraucher speist nicht ein. Stünde in seiner Zeile trotzdem ein
    Betrag — etwa nach einem Kategorie-Wechsel —, würde er sonst still zum
    Ertrag.
    """
    verbraucher = await _anlage(db, erloes=ERLOES_JE_MONAT,
                                kategorie="verbraucher", name="verbraucher")
    ohne = await _anlage(db, erloes=0.0, name="ohne")

    p_v = await get_finanz_prognose(anlage_id=verbraucher, monate=12, db=db)
    p_o = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    # Dieselbe Vorsicht: ohne Erträge wäre die Gleichheit trivial erfüllt.
    assert p_o.bisherige_ertraege_euro > 0, "keine Erträge — Fixture defekt"
    assert p_v.bisherige_ertraege_euro == pytest.approx(p_o.bisherige_ertraege_euro, abs=0.02)


async def test_erloes_steht_auf_der_zeile_seines_erzeugers(db):
    """Bauschritt 5 + 9: was komponentenscharf vorliegt, wird **zugeordnet**.

    ⚑ Beim Bau von Bauschritt 7 (2026-08-10) fiel auf, dass der gepflegte
    Erlös in der Zerlegung im **nicht zurechenbaren Rest** landete, obwohl
    seine Investition bekannt ist — die Bauschritt-5-Regel lautet „alles
    komponentenscharf Vorliegende direkt, nur Anlagengrößen werden verteilt".

    ⚠ Geprüft wird die **Differenz an derselben Zeile** zweier sonst
    identischer Anlagen, nicht ein Absolutwert: die Zeile trägt auch ihren
    Anteil am Erzeugungs-Erlös der Anlage, und der ist hier nicht das Thema.
    """
    erwartet = ERLOES_JE_MONAT * MONATE

    mit = await _anlage(db, erloes=ERLOES_JE_MONAT, name="mit")
    ohne = await _anlage(db, erloes=0.0, name="ohne")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)

    def _zeilen(p) -> dict[int, float]:
        return {e.investition_id: e.bisherige_ertraege_euro
                for e in (p.ertraege_je_investition or [])}

    z_mit, z_ohne = _zeilen(p_mit), _zeilen(p_ohne)
    # ⚠ **Ohne Erlös gibt es hier gar keine Zeile** — die Fixture hat keine
    # PV-Module, der Erzeugungs-Erlös der Anlage hat also keinen Schlüssel und
    # bleibt im Rest. Genau deshalb ist die Zeilen-SUMME die richtige Größe:
    # eine `max()`-Auswahl über ein leeres Dict wäre ein Fehler, und ein
    # Absolutwert würde den Anlagen-Anteil mitprüfen.
    assert z_mit, "der gepflegte Erlös erzeugt keine Zeile — Zuordnung fehlt"
    betrag_mit = sum(z_mit.values())
    betrag_ohne = sum(z_ohne.values())
    assert betrag_mit - betrag_ohne == pytest.approx(erwartet, abs=0.02), (
        "der gepflegte Erzeuger-Erlös gehört auf die Zeile seines Erzeugers — "
        "landet er im Rest, zeigt die Sicht dort 0 und der Rest wächst"
    )
    # Und im Rest steht er folglich **nicht**.
    assert (p_mit.ertraege_nicht_zurechenbar_euro or 0.0) == pytest.approx(
        p_ohne.ertraege_nicht_zurechenbar_euro or 0.0, abs=0.02
    )
