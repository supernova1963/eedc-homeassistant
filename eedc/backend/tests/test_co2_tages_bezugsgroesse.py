"""F-6 — der Tages-CO₂-Wert rechnet auf dem Eigenverbrauch, nicht auf der Erzeugung.

`services/energie_profil/tage_werte.py` war ein Überlebender der DI-2-Ablösung:
es stand dort ``erzeugung × CO2_FAKTOR_STROM_KG_KWH``, also die alte Formel, die
`berechne_co2_bilanz` (ADR-001) 2026 abgelöst hat. Damit bekam auch die
**eingespeiste** kWh die volle Netzstrom-Vermeidung gutgeschrieben — eine kWh,
die im Netz landet, verdrängt beim Betreiber keinen Netzbezug.

**Beweislage (Pflicht der Runde).** Der Erwartungswert ist ausgerechnet, nicht
aus einer zweiten Implementierung gezogen, und jede Zahl trägt die **Gegenprobe
auf den alten Wert**, damit sichtbar bleibt, wie weit die Erzeugungs-Formel
danebenlag. Rot gegen ``HEAD~1``:

  * ``test_tages_co2_rechnet_auf_dem_eigenverbrauch``  — 15,2 statt 38,0 kg
  * ``test_reiner_einspeisetag_spart_kein_co2``        — 0,0 statt 30,4 kg

Konstruktionsbedingt **grün** und deshalb ausdrücklich **Regressions-Schutz, kein
Beweis**: ``test_wp_strom_bewegt_den_tageswert_nicht``. Es hält die bewusste
Grenze fest, dass der Tag nur den PV-Anteil trägt — wer die Bilanz dort mit der
allein vorhandenen WP-Stromaufnahme „vervollständigt", erzeugt eine rein negative
WP-Komponente und damit eine Falschaussage.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.models import Anlage, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.tage_werte import baue_tage_werte

TAG = date(2026, 5, 10)


def _stunde(anlage_id: int, h: int, pv, vb, ei, nz, wp=None) -> TagesEnergieProfil:
    return TagesEnergieProfil(
        anlage_id=anlage_id, datum=TAG, stunde=h,
        pv_kw=pv, verbrauch_kw=vb, einspeisung_kw=ei, netzbezug_kw=nz,
        batterie_kw=None, waermepumpe_kw=wp,
    )


async def _anlage(db, stunden) -> Anlage:
    anlage = Anlage(anlagenname="Co2Tag", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add_all([_stunde(anlage.id, *args) for args in stunden])
    await db.flush()
    return anlage


@pytest.mark.asyncio
async def test_tages_co2_rechnet_auf_dem_eigenverbrauch(db):
    """Erzeugung 100 · Einspeisung 60 → Eigenverbrauch 40 kWh.

    Ausgerechnet:  40 kWh × 0,38 kg/kWh = **15,2 kg**
    Alter Wert:   100 kWh × 0,38 kg/kWh =   38,0 kg  (+150 %)
    """
    anlage = await _anlage(db, [
        (10, 50.0, 20.0, 30.0, 0.0),
        (11, 50.0, 20.0, 30.0, 0.0),
    ])

    tage = await baue_tage_werte(db, anlage, TAG, TAG)

    assert len(tage) == 1
    tag = tage[0]
    assert tag.erzeugung == 100.0
    assert tag.eigenverbrauch == 40.0

    assert tag.co2_einsparung == pytest.approx(15.2, abs=0.05)
    # Gegenprobe: der alte Rechenweg (Erzeugung × Faktor) ist damit verlassen.
    assert tag.co2_einsparung != pytest.approx(38.0, abs=0.05)

    # Dieselbe Bezugsgröße wie die Finanz-Spalte direkt daneben — CO₂ und € reden
    # am Tag jetzt über dieselben kWh (40 × 30 ct = 12,00 €).
    assert tag.ev_ersparnis == pytest.approx(12.0, abs=0.005)


@pytest.mark.asyncio
async def test_reiner_einspeisetag_spart_kein_co2(db):
    """Alles eingespeist → beim Betreiber wird kein Netzbezug verdrängt.

    Ausgerechnet:   0 kWh × 0,38 =  **0,0 kg**
    Alter Wert:    80 kWh × 0,38 =   30,4 kg — für Strom, der das Haus nie sah.
    """
    anlage = await _anlage(db, [
        (12, 80.0, 0.0, 80.0, 0.0),
    ])

    tage = await baue_tage_werte(db, anlage, TAG, TAG)

    assert tage[0].erzeugung == 80.0
    assert tage[0].eigenverbrauch == 0.0
    assert tage[0].co2_einsparung == pytest.approx(0.0, abs=0.05)
    assert tage[0].co2_einsparung != pytest.approx(80.0 * CO2_FAKTOR_STROM_KG_KWH, abs=0.05)


@pytest.mark.asyncio
async def test_wp_strom_bewegt_den_tageswert_nicht(db):
    """REGRESSIONS-SCHUTZ (vorher grün, zählt NICHT als Beweis).

    Stündlich liegt von der Wärmepumpe nur die **Stromaufnahme** vor, nie die
    erzeugte Wärmemenge. Wer damit `berechne_co2_bilanz` „vervollständigt",
    bekommt eine rein negative WP-Komponente. Der Tageswert bleibt deshalb
    bewusst der PV-Anteil — Σ Tage ≠ CO₂-Monatswert, sobald eine WP im Spiel ist,
    und das steht im Modul-Docstring statt still zu bleiben.
    """
    ohne_wp = await _anlage(db, [(10, 50.0, 20.0, 30.0, 0.0), (11, 50.0, 20.0, 30.0, 0.0)])
    mit_wp = await _anlage(db, [
        (10, 50.0, 20.0, 30.0, 0.0, 4.0),
        (11, 50.0, 20.0, 30.0, 0.0, 6.0),
    ])

    a = (await baue_tage_werte(db, ohne_wp, TAG, TAG))[0]
    b = (await baue_tage_werte(db, mit_wp, TAG, TAG))[0]

    assert b.wp_strom == 10.0, "die WP-Last ist im Fixture wirklich angekommen"
    # Bewusst OHNE Zusicherung auf den Zahlenwert: dieser Test soll die
    # Invariante halten, nicht den Fix beweisen. Mit einer 15,2 darin fiele er
    # gegen `HEAD~1` mit und zählte sich fälschlich zum Rot-Beweis.
    assert b.co2_einsparung == a.co2_einsparung
