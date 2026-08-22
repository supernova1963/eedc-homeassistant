"""D3 — der Daten-Checker kennt Verbrauchszähler (#377 · F-58 · N-294 · N-64).

**Die Ausgangslage, vor dem Bau gemessen:** `grep -ri zaehlerstand
services/daten_checker/` lieferte **0 Treffer**. Ein voller `check_anlage`-Lauf
gegen eine Anlage mit gepflegtem Gaszähler sagte über den Zählerstand
**nichts** — weder dass er fehlt, noch dass die Reihe bricht, noch dass das
Gerät auf inaktiv steht. Dafür sagte er einen Satz zu viel:
*„Gaszähler (sonstiges): Anschaffungskosten fehlen — Werden für ROI-Berechnung
benötigt."*

Jede Probe hier hält einen dieser Fälle fest, jede mit ihrer Gegenprobe.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity


# ─── Fixtures ────────────────────────────────────────────────────────────────

async def _anlage(db, *, mit_monatszeilen: bool = True) -> Anlage:
    a = Anlage(
        anlagenname="Haus mit Gas", leistung_kwp=10.0, standort_plz="10115",
        latitude=48.0, longitude=11.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(a)
    await db.flush()
    if mit_monatszeilen:
        # ⚠ Sitzung 86: `_erwartete_monate` zieht die Monate aus der ANLAGEN-
        # Liste. Eine Probe ohne diese Zeilen misst an mehreren Stellen nichts
        # und wäre trotzdem grün.
        for m in (1, 2, 3):
            db.add(Monatsdaten(
                anlage_id=a.id, jahr=2025, monat=m,
                einspeisung_kwh=100.0, netzbezug_kwh=200.0,
            ))
    await db.flush()
    return a


async def _zaehler(db, anlage, *, aktiv: bool = True, bezeichnung: str = "Gaszähler") -> Investition:
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung=bezeichnung,
        anschaffungsdatum=date(2025, 1, 1), aktiv=aktiv,
        parameter={"kategorie": "zaehler", "zaehler_art": "gas", "zaehler_einheit": "m³"},
    )
    db.add(inv)
    await db.flush()
    return inv


async def _staende(db, inv, werte: dict[int, float]) -> None:
    """Von Hand gepflegte Monatsend-Stände (der Ableser-Weg)."""
    for monat, stand in werte.items():
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=monat,
            verbrauch_daten={"zaehlerstand": stand},
        ))
    await db.flush()


async def _snapshots(db, anlage, inv, werte: list[tuple[datetime, float]]) -> None:
    from backend.services.zaehlerstaende import sensor_key_fuer
    for ts, wert in werte:
        db.add(SensorSnapshot(
            anlage_id=anlage.id, sensor_key=sensor_key_fuer(inv.id),
            zeitpunkt=ts, wert_kwh=wert,
        ))
    await db.flush()


async def _geladen(db, anlage_id: int) -> Anlage:
    """Die Anlage so laden, wie `check_anlage` sie lädt."""
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


def _kat(ergebnisse, kategorie):
    return [e for e in ergebnisse if e.kategorie == kategorie]


# ─── 1. Kommt überhaupt ein Stand an? (D3-a) ─────────────────────────────────

@pytest.mark.asyncio
async def test_zaehler_ohne_jeden_stand_wird_gemeldet(db):
    """Der Fall, über den der Checker bis D3 schwieg: das Gerät zeigt überall „—"."""
    a = await _anlage(db)
    await _zaehler(db, a)

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))

    treffer = _kat(erg, CheckKategorie.ZAEHLERSTAND_REIHE)
    assert len(treffer) == 1, [e.meldung for e in erg]
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "kein Zählerstand erfasst" in treffer[0].meldung
    # Beide Wege müssen dastehen — die Handpflege ist kein Notbehelf,
    # sondern für einen Gaszähler ohne Fernauslesung der vorgesehene Weg.
    assert "Monatsabschluss" in treffer[0].details
    assert "Datenquellen" in treffer[0].details


@pytest.mark.asyncio
async def test_handgepflegte_staende_sind_eine_vollwertige_quelle(db):
    """Gegenprobe — und die eigentliche P-6-Falle.

    Wer den Gaszähler abliest, hat **keinen** Sensor. Ein Check, der die
    Konfiguration statt der Daten prüft, meldet ihn dauerhaft als „ohne
    Quelle" — ein Hinweis, den er nur auflösen kann, indem er sich Hardware
    kauft, die er nicht braucht.
    """
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _staende(db, inv, {1: 1000.0, 2: 1050.0, 3: 1090.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))

    treffer = _kat(erg, CheckKategorie.ZAEHLERSTAND_REIHE)
    assert len(treffer) == 1, [e.meldung for e in erg]
    assert treffer[0].schwere == CheckSeverity.OK
    assert "3 Zählerstand-Ablesung(en)" in treffer[0].meldung


@pytest.mark.asyncio
async def test_ohne_zaehler_geraet_schweigt_die_kategorie_ganz(db):
    """Wer keinen Verbrauchszähler hat, bekommt die Kategorie gar nicht zu sehen."""
    a = await _anlage(db)
    db.add(Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0,
    ))
    await db.flush()

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert erg == []


# ─── 2. Läuft die Reihe rückwärts? (D3-d, N-294-Rest) ────────────────────────

@pytest.mark.asyncio
async def test_gefallener_stand_wird_erklaert_nicht_geheilt(db):
    """Konzept #377 §4: den Weg danebenstellen, nicht heilen."""
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _staende(db, inv, {1: 1200.0, 2: 1260.0, 3: 40.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))

    brueche = [
        e for e in _kat(erg, CheckKategorie.ZAEHLERSTAND_REIHE)
        if "Bruch" in e.meldung
    ]
    assert len(brueche) == 1, [e.meldung for e in erg]
    b = brueche[0]
    assert b.schwere == CheckSeverity.WARNING
    # Datum und BEIDE Stände — ohne sie sucht der Anwender die Stelle selbst.
    assert "31.03.2025" in b.details, b.details
    assert "1260" in b.details and "40" in b.details
    # ⛔ Kein Reparatur-Knopf: eedc weiß nicht, welcher Stand gilt.
    assert b.action_kind is None
    # Der Weg steht drin, und zwar vollständig — inklusive der Falle,
    # den Haken „aktiv" statt des Stilllegungsdatums zu benutzen.
    assert "Stilllegungsdatum" in b.details
    assert "aktiv" in b.details
    # ⚑ F-60-Klasse: v4.0.25 erzeugt diesen Bruch bei Bestandsanwendern SELBST.
    # Ohne diesen Satz schreibt die Meldung ihnen einen Fehler zu, den wir
    # gemacht haben.
    assert "4.0.25" in b.details, b.details


@pytest.mark.asyncio
async def test_bruch_mitten_im_zeitraum_faellt_nicht_durch(db):
    """Der Fall, den das Fenster-Flag NICHT sieht.

    `ZaehlerFenster.reihe_gebrochen` vergleicht Fenster-Anfang gegen
    Fenster-Ende. Steigt der Stand nach dem Bruch wieder über den Anfangswert,
    ist das Fenster unauffällig — der Bruch aber trotzdem da. Deshalb prüft der
    Checker **paarweise**.
    """
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _staende(db, inv, {1: 100.0, 2: 5.0, 3: 200.0})

    # Erst die Prämisse belegen: das Fenster-Flag ist hier blind.
    from backend.services.zaehlerstaende import lade_zaehlerstaende
    fenster = (await lade_zaehlerstaende(
        db, a.id, datetime(2025, 1, 1), datetime(2025, 12, 31),
    ))[0]
    assert fenster.reihe_gebrochen is False, "Prämisse hinfällig — Flag sieht es doch"
    assert fenster.differenz is not None

    # Und dann, dass der Checker ihn trotzdem findet.
    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert [e for e in erg if "Bruch" in e.meldung], [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_steigende_reihe_ist_kein_bruch(db):
    """Gegenprobe — sonst wäre der Check ein Dauerwarner."""
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _staende(db, inv, {1: 1000.0, 2: 1000.0, 3: 1090.0})  # Stillstand inklusive

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert not [e for e in erg if "Bruch" in e.meldung], [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_bruch_wird_auch_zwischen_zwei_snapshots_gefunden(db):
    """Der Sensor-Weg zählt genauso — ein Bruch liegt oft zwischen zwei Stunden."""
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _snapshots(db, a, inv, [
        (datetime(2025, 2, 1, 10, 0), 900.0),
        (datetime(2025, 2, 1, 11, 0), 905.0),
        (datetime(2025, 2, 1, 12, 0), 12.0),   # Zähler getauscht
    ])

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    brueche = [e for e in erg if "Bruch" in e.meldung]
    assert len(brueche) == 1, [e.meldung for e in erg]
    assert "01.02.2025" in brueche[0].details


# ─── 3. Auf inaktiv gesetzt (D3-e) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_inaktiver_zaehler_mit_ablesungen_bekommt_den_hinweis(db):
    """Der v4.0.23-Fallstrick: `aktiv=False` löscht die Historie aus jeder Sicht."""
    a = await _anlage(db)
    inv = await _zaehler(db, a, aktiv=False)
    await _staende(db, inv, {1: 1000.0, 2: 1050.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))

    hinweise = [e for e in erg if e.schwere == CheckSeverity.INFO]
    assert len(hinweise) == 1, [e.meldung for e in erg]
    assert "nicht aktiv" in hinweise[0].meldung
    assert "auch nicht für die Vergangenheit" in hinweise[0].details
    assert "Stilllegungsdatum" in hinweise[0].details
    # Der Hinweis führt in das Formular GENAU dieses Geräts.
    assert hinweise[0].link == f"/einstellungen/komponenten?bearbeiten={inv.id}"


@pytest.mark.asyncio
async def test_inaktiver_zaehler_ohne_ablesungen_schweigt(db):
    """Gegenprobe: ohne Ablesungen ist nichts zu verlieren — und „keine Quelle"
    wäre hier die zweite Nachricht über denselben Zustand."""
    a = await _anlage(db)
    await _zaehler(db, a, aktiv=False)

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert erg == [], [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_aktiver_zaehler_bekommt_keinen_inaktiv_hinweis(db):
    """Gegenprobe zur Gegenprobe."""
    a = await _anlage(db)
    inv = await _zaehler(db, a, aktiv=True)
    await _staende(db, inv, {1: 1000.0, 2: 1050.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert not [e for e in erg if e.schwere == CheckSeverity.INFO], [e.meldung for e in erg]


# ─── 4. Zuordnung zum Gerät (IA-V4 #243) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_befunde_tragen_ihre_investition(db):
    """Ohne `investition_id` filtert der Komponenten-Hub sie nicht heraus."""
    a = await _anlage(db)
    inv = await _zaehler(db, a)
    await _staende(db, inv, {1: 1200.0, 2: 40.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert erg
    assert all(e.investition_id == inv.id for e in erg), [
        (e.meldung, e.investition_id) for e in erg
    ]


@pytest.mark.asyncio
async def test_zwei_zaehler_werden_getrennt_beurteilt(db):
    """Ein Zählerstand ist eine Bestandsgröße — er summiert sich über nichts."""
    a = await _anlage(db)
    gut = await _zaehler(db, a, bezeichnung="Wasser")
    kaputt = await _zaehler(db, a, bezeichnung="Gas")
    await _staende(db, gut, {1: 10.0, 2: 12.0})
    await _staende(db, kaputt, {1: 900.0, 2: 5.0})

    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))

    brueche = [e for e in erg if "Bruch" in e.meldung]
    assert len(brueche) == 1
    assert brueche[0].investition_id == kaputt.id
    assert "Gas" in brueche[0].meldung
