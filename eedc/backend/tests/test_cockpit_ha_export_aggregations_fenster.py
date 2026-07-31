"""Cockpit/Übersicht + HA-Export an der Monats-Fakten-Schicht (Schritt **S4**).

S4 ist der Schritt **ohne** Inventur-Befund: beide Sichten rechnen heute richtig
und werden trotzdem umgehängt, weil eine selbst faltende Sicht die nächste
Drift-Quelle ist (`docs/KONZEPT-MONATS-FAKTEN.md` §11). Der Beweis dafür ist
negativ und steht woanders — die Vier-Wege-Symmetrie und
`test_co2_autarkie_sichten_symmetrie.py` bleiben über alle vier Achsen
**unverändert** grün.

Diese Datei prüft, was der Umbau **an den Rändern** ändert. Drei davon sind echte
Korrekturen, die erst beim Umhängen sichtbar wurden; die vierte ist reiner
Regressions-Schutz und ist als solcher ausgewiesen:

- **N-10 · Der Jahres-Filter des Cockpits erfasste die PV nicht.** `?jahr=` hat
  die IMD- und die Monatsdaten-Query gefiltert, `lade_pv_je_monat` aber nicht —
  in der Erzeugungs-Kachel, im spezifischen Ertrag und in der ganzen
  Energiebilanz stand die PV **aller** Jahre. Kein Frontend-Aufrufer übergibt
  heute ein Jahr (`komponentenAdapter.tsx` ruft ohne), deshalb hat es niemand
  gemeldet. Rot gegen `HEAD~1`.
- **N-11 · Der HA-Export hat stillgelegte Komponenten rückwirkend ausgeblendet.**
  Seine Investitions-Query lief über `aktiv_jetzt()` — ein SQL-Vorfilter auf den
  HEUTIGEN Zustand, der die ganze Historie einer stillgelegten Komponente
  mitgenommen hat. #123 trennt genau hier: `aktiv=False` = wie gelöscht
  (nirgends), **stillgelegt** = bis zum Stilllegungsdatum aktiv (Daten fließen
  ein). Die Schicht filtert je Monat über `ist_aktiv_im_monat`. Rot gegen
  `HEAD~1`.
- **Der Dienstwagen fehlte in der V2H-Bilanz des HA-Exports.** Seine V2H-Schleife
  kannte `ist_dienstlich` nicht, das Cockpit schon — dieselbe Anlage nannte in
  HA einen anderen Eigenverbrauch als auf dem Bildschirm
  ([[feedback_dienstwagen_alle_checks]]). Rot gegen `HEAD~1`.
- **Der E-Mob-Pool bleibt über den Zeitraum gepoolt** (Falle 3 der S1-Übergabe) —
  **Regressions-Schutz, kein Fix-Beweis**: der Test war vorher grün. Er nagelt
  fest, dass das Umhängen die Poolung nicht von „einmal global" auf „Σ der
  Monate" verschoben hat; das sind zwei verschiedene Zahlen, und die Verschiebung
  wäre still passiert.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

ANSCHAFFUNG = date(2024, 1, 1)


def _sensor(werte, key: str):
    """Ein Sensorwert aus der HA-Export-Liste — mit lesbarer Meldung, wenn er fehlt."""
    treffer = [w for w in werte if w.definition.key == key]
    assert treffer, (
        f"kein Sensor `{key}` — vorhanden: {sorted(w.definition.key for w in werte)}"
    )
    return treffer[0].value


async def _basis_anlage(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=0.0,
    ))
    return anlage


# ═══════════════════════════════════════════════════════════════════════
# N-10 — der Jahres-Filter des Cockpits
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jahresfilter_begrenzt_pv_und_energiebilanz_der_cockpit_uebersicht(db):
    """`?jahr=2025` darf nicht die PV von 2026 mitzählen.

    Zwei Jahre, je ein Monat, klar getrennte Größen:

        2025-06   PV 1.000 kWh   Einspeisung 400   Netzbezug 100
        2026-06   PV 3.000 kWh   Einspeisung 900   Netzbezug 200

    Bis 2026-07-31 stand für **beide** Jahresabfragen dieselbe PV-Summe
    (4.000 kWh) in der Kachel, weil `lade_pv_je_monat` ohne Jahres-Argument
    aufgerufen wurde — während Einspeisung und Netzbezug korrekt gefiltert
    waren. Die Energiebilanz mischte damit die Erzeugung von zwei Jahren mit den
    Zählerwerten von einem.
    """
    anlage = await _basis_anlage(db, "Jahresfilter")
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=900.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 3000.0}))
    await db.commit()

    y2025 = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=db)
    y2026 = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2026, db=db)
    alle = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    assert y2025.pv_erzeugung_kwh == pytest.approx(1000.0)
    assert y2026.pv_erzeugung_kwh == pytest.approx(3000.0)
    assert alle.pv_erzeugung_kwh == pytest.approx(4000.0)

    # Und die Bilanz zieht mit: Eigenverbrauch 2025 = 1.000 − 400 = 600 kWh,
    # Gesamtverbrauch 700, Autarkie 85,7 %. Vorher stand hier die 4.000er-PV
    # gegen die Zählerwerte eines Jahres → Autarkie praktisch 100 %.
    assert y2025.eigenverbrauch_kwh == pytest.approx(600.0)
    assert y2025.autarkie_prozent == pytest.approx(85.7, abs=0.1)
    assert y2026.eigenverbrauch_kwh == pytest.approx(2100.0)

    # Ein Jahres-Schnitt ist nie größer als die ganze Historie.
    assert y2025.pv_erzeugung_kwh < alle.pv_erzeugung_kwh
    assert y2025.anzahl_monate == 1 and alle.anzahl_monate == 2


# ═══════════════════════════════════════════════════════════════════════
# N-11 — stillgelegte Komponenten im HA-Export
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ha_export_traegt_die_historie_einer_stillgelegten_komponente(db):
    """Ein 2025 stillgelegter Speicher zählt in der Lebenszeit-Bilanz weiter mit.

        PV 1.000   Einspeisung 400   Netzbezug 100
        Speicher   Ladung 300   Entladung 250   (stillgelegt zum 31.12.2025)

        Direktverbrauch = 1.000 − 400 − 300 = 300 kWh
        Eigenverbrauch  = 300 + 250         = 550 kWh
        Gesamtverbrauch = 550 + 100         = 650 kWh
        Autarkie        = 550 / 650         =  84,6 %

    Bis 2026-07-31 hat der HA-Export seine Investitionen über `aktiv_jetzt()`
    geladen — ein Vorfilter auf den heutigen Zustand. Der stillgelegte Speicher
    fiel damit komplett aus der Historie: Eigenverbrauch 600 statt 550 kWh,
    Autarkie 85,7 statt 84,6 %, und die beiden Speicher-Sensoren verschwanden.
    Das Cockpit hat denselben Monat nie so gerechnet (#123/#236) — die Sensoren
    in HA behaupteten etwas anderes als der Bildschirm.
    """
    anlage = await _basis_anlage(db, "Stillgelegter Speicher")
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=12000.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Alt-Akku",
                           leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                           stilllegungsdatum=date(2025, 12, 31),
                           anschaffungskosten_gesamt=8000.0)
    db.add_all([pv, speicher])
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=speicher.id, jahr=2025, monat=6,
                                  verbrauch_daten={"ladung_kwh": 300.0,
                                                   "entladung_kwh": 250.0}))
    await db.commit()

    werte = await calculate_anlage_sensors(db, anlage)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") == pytest.approx(550.0)
    assert _sensor(werte, "autarkie_prozent") == pytest.approx(84.6, abs=0.1)
    assert _sensor(werte, "direktverbrauch_gesamt_kwh") == pytest.approx(300.0)

    # Gegenprobe auf den Stand vor dem Umbau (Speicher ganz weg).
    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") != pytest.approx(600.0)

    # Und deckungsgleich mit dem Cockpit — es hat diesen Monat immer so gerechnet.
    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") == pytest.approx(
        cockpit.eigenverbrauch_kwh, abs=0.1
    )
    assert _sensor(werte, "autarkie_prozent") == pytest.approx(
        cockpit.autarkie_prozent, abs=0.1
    )


@pytest.mark.asyncio
async def test_ha_export_filtert_den_dienstwagen_aus_der_v2h_bilanz(db):
    """V2H eines Dienstwagens ist keine private Ersparnis — auch nicht in HA.

        PV 1.000   Einspeisung 400   Netzbezug 100   V2H (dienstlich) 100

        Eigenverbrauch = 1.000 − 400 = 600 kWh   (V2H zählt NICHT)
        Autarkie       = 600 / 700   =  85,7 %

    Die V2H-Schleife des HA-Exports kannte `ist_dienstlich` nicht und rechnete
    700 kWh / 87,5 % — das Cockpit auf derselben Anlage 600 kWh / 85,7 %.
    """
    anlage = await _basis_anlage(db, "Dienstwagen-V2H")
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=12000.0)
    dienstwagen = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Firmenwagen",
                              anschaffungsdatum=ANSCHAFFUNG,
                              anschaffungskosten_gesamt=30000.0,
                              parameter={"ist_dienstlich": True, "nutzt_v2h": True})
    db.add_all([pv, dienstwagen])
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=dienstwagen.id, jahr=2025, monat=6,
                                  verbrauch_daten={"v2h_entladung_kwh": 100.0}))
    await db.commit()

    werte = await calculate_anlage_sensors(db, anlage)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") == pytest.approx(600.0)
    assert _sensor(werte, "autarkie_prozent") == pytest.approx(85.7, abs=0.1)
    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") != pytest.approx(700.0)
    assert _sensor(werte, "eigenverbrauch_gesamt_kwh") == pytest.approx(
        cockpit.eigenverbrauch_kwh, abs=0.1
    )


# ═══════════════════════════════════════════════════════════════════════
# Falle 3 — Regressions-Schutz, kein Fix-Beweis
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_emob_pool_bleibt_ueber_den_ganzen_zeitraum_gepoolt(db):
    """**Regressions-Schutz** (vorher grün): einmal global poolen, nicht Σ Monate.

    `get_emob_heimladung_canonical` wählt die Quelle **strukturell**: existiert
    eine Wallbox mit Heimladung, ist sie die Wahrheit — komplett, nicht feldweise
    (#262). Diese Wahl über den ganzen Zeitraum EINMAL zu treffen ist etwas
    anderes, als sie in jedem Monat neu zu treffen:

        Mai   E-Auto 100 kWh · Wallbox   0 kWh   → monatsweise: E-Auto 100
        Juni  E-Auto  50 kWh · Wallbox 120 kWh   → monatsweise: Wallbox 120

        Σ der Monatsentscheidungen                            = 220 kWh
        EINE Entscheidung über den Zeitraum (Wallbox trägt)   = 120 kWh

    Das Cockpit poolt seit jeher global. Die Schicht entscheidet je Monat und
    reicht deshalb die bereits dienstwagen- und laufzeitgefilterten Rohdicts mit
    durch (`emob.eauto_ladedaten` / `wallbox_ladedaten`), damit dieselbe globale
    Poolung über denselben SoT laufen kann. Ohne diesen Durchgriff hätte S4 die
    Zahl **still** von 120 auf 220 verschoben.
    """
    anlage = await _basis_anlage(db, "Emob-Pool-Fenster")
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Kombi",
                        anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=30000.0)
    wallbox = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Ladepunkt",
                          anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=1200.0)
    db.add_all([eauto, wallbox])
    await db.flush()
    for monat in (5, 6):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=0.0, netzbezug_kwh=300.0))
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2025, monat=5,
        verbrauch_daten={"km_gefahren": 500.0, "ladung_kwh": 100.0,
                         "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 40.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2025, monat=6,
        verbrauch_daten={"km_gefahren": 500.0, "ladung_kwh": 50.0,
                         "ladung_pv_kwh": 30.0, "ladung_netz_kwh": 20.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=wallbox.id, jahr=2025, monat=5,
        verbrauch_daten={"ladung_kwh": 0.0, "ladung_pv_kwh": 0.0, "ladung_netz_kwh": 0.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=wallbox.id, jahr=2025, monat=6,
        verbrauch_daten={"ladung_kwh": 120.0, "ladung_pv_kwh": 90.0,
                         "ladung_netz_kwh": 30.0}))
    await db.commit()

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    assert cockpit.emob_ladung_kwh == pytest.approx(120.0), (
        "der Pool wird EINMAL über den Zeitraum gebildet, nicht je Monat"
    )
    assert cockpit.emob_ladung_kwh != pytest.approx(220.0)
    # Der PV-Anteil kommt aus derselben Quelle — 90 von 120.
    assert cockpit.emob_pv_anteil_prozent == pytest.approx(75.0, abs=0.1)
    # km bleiben beim E-Auto und werden monatsweise summiert.
    assert cockpit.emob_km == pytest.approx(1000.0)
