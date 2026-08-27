"""Daten-Checker: mehrere verschiedene Modus-Quellen an EINEM Gerät (N-340).

## Warum diese Datei nötig ist

Der Check fragte bis zum 27.08.2026 `_hat_modus` — *„gibt es IRGENDEINE
Modus-Zuordnung?"*. Die Aufteilung braucht aber **eine eindeutige Quelle**: Der
Stromzähler des Geräts ist einer, und aus N Innengeräte-Zuständen einen
Anlagen-Zustand zu bilden hängt an der fremden Maschine (ADR-002/P4).

Beide Seiten liefen damit auseinander: Wer drei Innengeräte auf drei
verschiedene `climate`-Entitäten legte, bekam **keine Aufteilung** — und der
Daten-Checker meldete grün *„Betriebsmodus ist zugeordnet"*. Eine Meldung, die
den Anwender in die Irre führt, ist schlimmer als keine (SOLL §6).

⚠ **Und die dritte Meldung ist der eigentliche Punkt:** Wer mehrdeutig
zugeordnet hat, darf **nicht** den Text „Betriebsmodus nicht zugeordnet"
bekommen — er hat zugeordnet. Ihm fehlt die Eindeutigkeit, und der Weg dorthin
ist ein anderer.

Schwesterdateien: `test_n340_modus_quelle.py` (die Regel `modus_quelle` selbst),
`test_263_k2_betriebsmodus_lesen_mitschreiben.py` (ob der **Aggregationspfad** sie
benutzt) und `test_daten_checker_connector_monatswert.py` (dieselbe Bauform: eine
eingerichtete Quelle, die still nichts liefert). Die drei zusammen decken die
Kette Regel → Rechnung → Auskunft; einzeln deckt keine davon den Fund ab.
"""

from __future__ import annotations

from datetime import date

from backend.models import Anlage, Investition
from backend.services.daten_checker import CheckKategorie, DatenChecker


async def _anlage_mit_klima(db, mapping: dict, geraete: int = 1) -> Anlage:
    anlage = Anlage(anlagenname="K", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    ids = []
    for n in range(geraete):
        inv = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"Klima {n + 1}",
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
            parameter={"wp_art": "luft_luft"},
        )
        db.add(inv)
        await db.flush()
        ids.append(inv.id)
    anlage.sensor_mapping = {"investitionen": {
        str(inv_id): mapping for inv_id in ids
    }}
    await db.commit()
    return anlage


async def _befunde(db, anlage):
    return await DatenChecker(db=db)._check_klima_modus_sensor(anlage)


async def test_eine_quelle_je_innengeraet_meldet_ok(db):
    """Der Bestandsfall darf nicht rot werden: dieselbe Entität überall (D3)."""
    anlage = await _anlage_mit_klima(db, {"live": {
        "betriebsmodus-3": "climate.a", "betriebsmodus-4": "climate.a",
    }})
    befunde = await _befunde(db, anlage)
    assert len(befunde) == 1
    assert befunde[0].schwere == "ok"
    assert "zugeordnet" in befunde[0].meldung


async def test_verschiedene_quellen_melden_die_mehrdeutigkeit(db):
    """Der Fund: vorher meldete genau diese Anlage „ist zugeordnet"."""
    anlage = await _anlage_mit_klima(db, {"live": {
        "betriebsmodus-3": "climate.a", "betriebsmodus-4": "climate.b",
    }})
    befunde = await _befunde(db, anlage)
    assert len(befunde) == 1
    b = befunde[0]
    assert b.kategorie == CheckKategorie.KLIMA_MODUS_SENSOR.value
    assert "mehrere verschiedene Modus-Quellen" in b.meldung
    # ⚠ NICHT der Text für „gar nicht zugeordnet" — er hat ja zugeordnet.
    assert "nicht zugeordnet" not in b.meldung
    # Der Ausweg gehört dazu (SOLL §6: Ursache UND Ausweg).
    assert "Template-Sensor" in b.details
    assert "dieselbe climate-Entität" in b.details


async def test_gar_keine_zuordnung_behaelt_ihren_eigenen_text(db):
    """Die Gegenrichtung — sonst hätte ich einen Text durch den anderen ersetzt."""
    anlage = await _anlage_mit_klima(db, {"live": {}})
    befunde = await _befunde(db, anlage)
    assert len(befunde) == 1
    assert "Betriebsmodus nicht zugeordnet" in befunde[0].meldung
    assert "mehrere verschiedene" not in befunde[0].meldung


async def test_gemischt_meldet_BEIDE_geraete(db):
    """⚠ Mein erster Entwurf gab nur die mehrdeutigen zurück und liess die
    unzugeordneten fallen — eine Anlage kann beides haben.
    """
    anlage = Anlage(anlagenname="K", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv_a = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Mehrdeutig",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        parameter={"wp_art": "luft_luft"})
    inv_b = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Ohne",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        parameter={"wp_art": "luft_luft"})
    db.add_all([inv_a, inv_b])
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {
        str(inv_a.id): {"live": {"betriebsmodus-3": "climate.a",
                                 "betriebsmodus-4": "climate.b"}},
        str(inv_b.id): {"live": {}},
    }}
    await db.commit()

    befunde = await _befunde(db, anlage)
    assert len(befunde) == 2, "beide Geräte müssen gemeldet werden"
    texte = {b.investition_id: b.meldung for b in befunde}
    assert "mehrere verschiedene Modus-Quellen" in texte[inv_a.id]
    assert "Betriebsmodus nicht zugeordnet" in texte[inv_b.id]
