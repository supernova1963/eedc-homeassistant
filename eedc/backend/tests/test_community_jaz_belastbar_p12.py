"""ADR-002/**P12** an der Repo-Grenze — der Server darf keine JAZ aus einem
Mischquotienten bilden (Fund N-367).

**Warum es diesen Test gibt.** Lokal entscheidet seit dem 26.08. der Layer, ob
eine Arbeitszahl entstehen darf. Der Community-Server bildet seinen JAZ aber
**selbst**, an fünf Stellen — er hat die Geräte nie gesehen, nur ihre Summen.
Ohne das Flag `wp_jaz_belastbar` ginge eine Anlage mit Wärmepumpe **und**
Split-Klimaanlage mit dem Strom zweier Geräte und der Wärme von einem in
**fremde** Vergleichswerte ein: an 126 Anlagen gemessen (02.09.2026) tragen die
Regionen zwischen 3 und 11 Wärmepumpen — bei n≈4 verzieht ein einzelner
Mischquotient den angezeigten Regionalwert sichtbar.

**Schwesterdateien:** `test_community_payload_monats_fakten.py` (die Payload-Schicht,
ADR-002/P10), `test_community_payload_f47_f48.py` (Monatsauswahl im Payload) und
`test_p12_arbeitszahl_alle_wege.py` — der **Symmetriepartner**: dort steht dieselbe
Regel für die lokalen Sichten, hier für die Repo-Grenze.

⛔ **Der Test prüft BEIDE Hälften der Regel**, weil eine allein die falsche
Lösung nicht ausschließt: Das Flag muss die **Kennzahl** sperren **und** die
**Mengen** stehen lassen (E1 — Mengen summiert, Kennzahlen getrennt). Ein
Payload, der bei verletzter Abgrenzung die Wärme weglässt, wäre grün in der
ersten Hälfte und beschädigte die Mengen-Auswertungen des Servers.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.services.community_service import prepare_community_data


async def _anlage_mit_wp(db, *, mit_klimaanlage: bool) -> int:
    """Eine Anlage mit Wärmepumpe — wahlweise plus Split-Klimaanlage.

    Die Zahlen sind die des Melders (T89667 #290): 210 kWh Wärme, 97 kWh
    WP-Strom (⇒ 2,2), und die Klimaanlage bringt 219 kWh Strom ohne Wärme
    (⇒ gemeinsam 0,7).
    """
    anlage = Anlage(anlagenname="P12", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # Zählerzeile: ohne sie kennt der Payload den Monat nicht.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=7,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=7,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1100.0}))

    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Luft-Wasser",
                     anschaffungsdatum=date(2024, 1, 1),
                     parameter={"wp_art": "luft_wasser"})
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2026, monat=7,
        verbrauch_daten={"stromverbrauch_kwh": 97.0, "warmwasser_kwh": 210.0},
    ))

    if mit_klimaanlage:
        klima = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Split",
                            anschaffungsdatum=date(2024, 1, 1),
                            parameter={"wp_art": "luft_luft"})
        db.add(klima)
        await db.flush()
        # Strom ja, Wärme nein — bauartbedingt gibt es dort keinen Zähler.
        db.add(InvestitionMonatsdaten(
            investition_id=klima.id, jahr=2026, monat=7,
            verbrauch_daten={"stromverbrauch_kwh": 219.0},
        ))

    await db.commit()
    return anlage.id


def _juli(data) -> dict:
    return next(m for m in data["monatswerte"] if (m["jahr"], m["monat"]) == (2026, 7))


@pytest.mark.asyncio
async def test_reine_waermepumpe_ist_belastbar(db):
    """Gegenprobe zuerst: ohne Mischung trägt der Payload `True`.

    Ohne sie wäre der Test unten auch dann grün, wenn das Flag **immer** `False`
    wäre — und der Server bekäme nie wieder eine Arbeitszahl.
    """
    anlage_id = await _anlage_mit_wp(db, mit_klimaanlage=False)
    juli = _juli(await prepare_community_data(db, anlage_id))

    assert juli["wp_jaz_belastbar"] is True
    assert juli["wp_stromverbrauch_kwh"] == pytest.approx(97.0, abs=0.1)


@pytest.mark.asyncio
async def test_waermepumpe_plus_klimaanlage_ist_nicht_belastbar(db):
    """Der Melderfall: zwei Bauarten, eine Wärmequelle ⇒ keine Kennzahl."""
    anlage_id = await _anlage_mit_wp(db, mit_klimaanlage=True)
    juli = _juli(await prepare_community_data(db, anlage_id))

    assert juli["wp_jaz_belastbar"] is False, (
        "Zwei Bauarten in einem Quotienten: der Server würde 210/316 = 0,7 "
        "bilden und in den Regionalwert seiner Nachbarn tragen."
    )


@pytest.mark.asyncio
async def test_die_mengen_bleiben_vollstaendig_erhalten(db):
    """**Die zweite Hälfte der Regel (E1).** Gesperrt ist die Kennzahl, nie die Menge.

    Der Server braucht die Wärme- und Stromsummen für `components.py`,
    `statistics.py` und `benchmark.py`; sie wegzulassen heilte eine Kennzahl und
    beschädigte fünf Mengen-Auswertungen.
    """
    anlage_id = await _anlage_mit_wp(db, mit_klimaanlage=True)
    juli = _juli(await prepare_community_data(db, anlage_id))

    assert juli["wp_jaz_belastbar"] is False
    # Strom BEIDER Geräte — additiv und richtig.
    assert juli["wp_stromverbrauch_kwh"] == pytest.approx(316.0, abs=0.1)
    assert juli["wp_warmwasser_kwh"] == pytest.approx(210.0, abs=0.1)


@pytest.mark.asyncio
async def test_das_flag_faehrt_bei_jeder_wp_anlage_mit(db):
    """P4: Ein fehlendes Feld hieße beim Server „alter Client, unbekannt".

    `None` und `True` sind dort verschiedene Aussagen — die erste zählt als
    Altbestand mit, die zweite ist eine Messung. Ein Payload, der das Feld nur
    im Verletzungsfall setzt, machte aus jeder sauberen Anlage einen Altbestand.
    """
    for mit_klima in (False, True):
        anlage_id = await _anlage_mit_wp(db, mit_klimaanlage=mit_klima)
        juli = _juli(await prepare_community_data(db, anlage_id))
        assert "wp_jaz_belastbar" in juli
        assert isinstance(juli["wp_jaz_belastbar"], bool)
