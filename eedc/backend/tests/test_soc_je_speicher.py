"""Der Anlagen-Ladestand ist der aller Speicher, nicht der des ersten (N-239).

**Der Fehler, gegen den diese Datei steht** (am Code gemessen 2026-08-12):
`_get_soc_history` sammelte alle gemappten SoC-Sensoren ein, nahm dann aber den
**ersten mit Daten** und brach ab — `return` im LTS-Pfad, `break  # Erstes
SoC-Entity reicht` im History-Pfad. `TagesEnergieProfil.soc_prozent` trug damit
bei zwei Speichern den Ladestand *eines* Geräts, und welches, entschied die
Reihenfolge im Sensor-Mapping. Fünf Stellen im Baum behaupteten dabei
„anlagenweiter Mischwert".

**Die wichtigste Prüfung ist die erste:** bei genau einem Speicher — dem
Normalfall — muss die Umstellung ein **No-op** sein. Ohne diese Zusicherung
wäre sie vor einem Release nicht vertretbar.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.speicher import anlagen_soc_prozent


# ------------------------------------------------- die No-op-Zusicherung --


@pytest.mark.parametrize("soc", [0.0, 13.7, 50.0, 99.9, 100.0])
def test_ein_speicher_ist_exakt_sein_eigener_ladestand(soc):
    """Der Normalfall bleibt bitgenau, wie er war — für JEDEN Wert.

    Das ist die Zusicherung, die die Umstellung vor dem Release trägt: eine
    Anlage mit einem Speicher sieht keine Änderung an Vollzyklen, SoC-Hüben,
    Heatmap oder Kalibrierung.
    """
    assert anlagen_soc_prozent({7: soc}, {7: 12.1}) == pytest.approx(soc)


def test_ein_speicher_auch_ohne_gepflegte_kapazitaet():
    """Ohne Kapazität gibt es nichts zu gewichten — der Wert bleibt derselbe."""
    assert anlagen_soc_prozent({7: 42.0}, {}) == pytest.approx(42.0)


# ------------------------------------------------------ die Gewichtung --


def test_gewichtet_wird_nach_kapazitaet_nicht_nach_kopfzahl():
    """15 kWh auf 20 % + 5 kWh auf 100 % sind 40 %, nicht 60 %.

    Das arithmetische Mittel behauptete 60 % — und damit anderthalb Mal so viel
    Energie, wie tatsächlich im Haus steht. Genau diese Verwechslung wäre die
    naheliegende „Reparatur" des ersten Treffers gewesen.
    """
    assert anlagen_soc_prozent({1: 20.0, 2: 100.0}, {1: 15.0, 2: 5.0}) == pytest.approx(40.0)
    # Die Gegenprobe: das ungewichtete Mittel wäre 60 %.
    assert (20.0 + 100.0) / 2 == pytest.approx(60.0)


def test_reihenfolge_aendert_nichts():
    """Der alte Fehler hing an der Mapping-Reihenfolge — der neue Wert nicht."""
    a = anlagen_soc_prozent({1: 20.0, 2: 100.0}, {1: 15.0, 2: 5.0})
    b = anlagen_soc_prozent({2: 100.0, 1: 20.0}, {2: 5.0, 1: 15.0})
    assert a == pytest.approx(b)


def test_ohne_kapazitaet_eines_geraets_wird_ungewichtet_gemittelt():
    """Eine erfundene Gewichtung wäre schlechter als eine ehrlich gleiche.

    Und ein Gerät wegzulassen wäre still eine andere Anlage — deshalb fällt die
    Rechnung auf das arithmetische Mittel zurück, statt zu raten oder zu kürzen.
    """
    assert anlagen_soc_prozent({1: 20.0, 2: 100.0}, {1: 15.0}) == pytest.approx(60.0)


def test_geraet_ohne_ladestand_zaehlt_nicht_als_null():
    """Ein fehlender Ladestand ist keine 0 — sonst zöge er die Anlage nach unten."""
    assert anlagen_soc_prozent({1: 80.0, 2: None}, {1: 10.0, 2: 10.0}) == pytest.approx(80.0)


def test_ohne_jeden_ladestand_gibt_es_keinen_anlagenwert():
    assert anlagen_soc_prozent({}, {1: 10.0}) is None
    assert anlagen_soc_prozent({1: None}, {1: 10.0}) is None


def test_null_kapazitaeten_kippen_die_rechnung_nicht():
    """Division durch 0 ist kein Ladestand — dann eben ungewichtet."""
    assert anlagen_soc_prozent({1: 30.0, 2: 70.0}, {1: 0.0, 2: 0.0}) == pytest.approx(50.0)


# ------------------------------------------- die Quelle liest alle Geräte --


async def test_soc_history_liefert_jedes_geraet_statt_des_ersten(db, monkeypatch):
    """Der eigentliche Fehlgriff, an der Quelle geprüft.

    Zwei Speicher mit je eigenem SoC-Sensor: die History muss **beide**
    zurückgeben. Vorher gewann der erste, und der zweite existierte für die
    ganze Auswertungskette nicht.
    """
    from datetime import date

    from backend.models import Anlage, Investition
    from backend.services.energie_profil import _helpers

    anlage = Anlage(anlagenname="Zwei Speicher", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    gross = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Gross",
                        anschaffungsdatum=date(2024, 1, 1),
                        parameter={"nutzbare_kapazitaet_kwh": 15.0})
    klein = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Klein",
                        anschaffungsdatum=date(2024, 1, 1),
                        parameter={"nutzbare_kapazitaet_kwh": 5.0})
    db.add_all([gross, klein])
    await db.commit()

    mapping = {"investitionen": {
        str(gross.id): {"live": {"soc": "sensor.gross_soc"}},
        str(klein.id): {"live": {"soc": "sensor.klein_soc"}},
    }}

    class _Stats:
        is_available = True

        def get_hourly_sensor_data(self, entities, von, bis):
            return {
                "sensor.gross_soc": {von.isoformat(): {8: 20.0}},
                "sensor.klein_soc": {von.isoformat(): {8: 100.0}},
            }

    monkeypatch.setattr(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        lambda: _Stats(),
    )

    je_stunde = await _helpers._get_soc_history(anlage, mapping, date(2026, 6, 1), db)

    assert je_stunde[8] == {gross.id: 20.0, klein.id: 100.0}, (
        "der zweite Speicher fehlte — genau der Fehlgriff aus N-239"
    )
    # Und der Anlagenwert daraus ist der gewichtete, nicht der des ersten.
    kapazitaeten = {gross.id: 15.0, klein.id: 5.0}
    assert anlagen_soc_prozent(je_stunde[8], kapazitaeten) == pytest.approx(40.0)


# ------------------------------------------- der Daten-Checker-Befund N-239 --


async def _anlage_mit_speichern(db, *, anzahl_mit_soc: int):
    from datetime import date

    from backend.models import Anlage, Investition

    anlage = Anlage(anlagenname="SoC-Checker", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    ids = []
    for i in range(max(anzahl_mit_soc, 1)):
        inv = Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung=f"Speicher {i}",
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"nutzbare_kapazitaet_kwh": 10.0},
        )
        db.add(inv)
        await db.flush()
        ids.append(inv.id)
    anlage.sensor_mapping = {"investitionen": {
        str(inv_id): {"live": {"soc": f"sensor.soc_{inv_id}"}}
        for inv_id in ids[:anzahl_mit_soc]
    }}
    return anlage, ids


async def _befunde(db, anlage):
    from backend.services.daten_checker import DatenChecker

    return await DatenChecker(db)._check_soc_nur_ein_speicher(anlage)


async def test_checker_meldet_alt_tage_einer_mehrspeicher_anlage(db):
    """Die Signatur ist eindeutig: `soc_je_speicher IS NULL` bei ≥ 2 Sensoren."""
    from datetime import date

    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage, _ = await _anlage_mit_speichern(db, anzahl_mit_soc=2)
    for tag in (date(2026, 6, 1), date(2026, 6, 2)):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=12,
            soc_prozent=50.0, soc_je_speicher=None,
        ))
    await db.commit()

    befunde = await _befunde(db, anlage)

    assert len(befunde) == 1
    assert befunde[0].schwere == "warning"
    assert "2 Tag(e)" in befunde[0].meldung
    assert befunde[0].action_kind == "reaggregate_range", "der Knopf steht daneben"
    assert "Erzeugung, Verbrauch und Netzbezug sind es NICHT" in befunde[0].details


async def test_checker_schweigt_bei_einem_speicher(db):
    """Die entscheidende Abgrenzung — dort war die alte Rechnung wertgleich.

    Ohne sie bekäme die überwiegende Mehrheit der Anlagen eine Warnung über
    einen Fehler, den sie nie hatte.
    """
    from datetime import date

    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage, _ = await _anlage_mit_speichern(db, anzahl_mit_soc=1)
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=date(2026, 6, 1), stunde=12,
        soc_prozent=50.0, soc_je_speicher=None,
    ))
    await db.commit()

    assert await _befunde(db, anlage) == []


async def test_checker_meldet_ok_wenn_die_historie_aufgeschluesselt_ist(db):
    from datetime import date

    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage, ids = await _anlage_mit_speichern(db, anzahl_mit_soc=2)
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=date(2026, 6, 1), stunde=12,
        soc_prozent=50.0,
        soc_je_speicher={str(ids[0]): 20.0, str(ids[1]): 80.0},
    ))
    await db.commit()

    befunde = await _befunde(db, anlage)

    assert len(befunde) == 1 and befunde[0].schwere == "ok"
