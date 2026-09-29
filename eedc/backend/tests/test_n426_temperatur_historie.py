"""**N-426-Nachtrag** — die Ø-Temperatur der Historie hat einen Handgriff.

Der Wetter-Auto-Fill des Monatsformulars lebte in der V3-Seite und ist mit dem
IA-V4-Flip (`243944e5`, 25.07.2026) samt ihr gelöscht worden; mit WK-03
(`fe28f49e`, 13.09.2026) ist er zurück. **Er wirkt nach vorn.** Jeder Monat, der
dazwischen abgeschlossen wurde, trägt in `Monatsdaten.durchschnittstemperatur`
weiterhin ``NULL`` — an der Demo-Anlage gemessen (11.09.): 34 von 34.

⭐ **Die Zeile nennt zwei Zahlen, und beide gehören dazu.** *„n Monate ohne
Ø Temperatur"* allein wäre eine Aufgabe ohne Weg; *„für m davon reicht die
Messreihe"* sagt, was der Knopf leisten kann. Für die übrigen gibt es **keinen**
Knopf: dort hilft nur der Auto-Fill im Monat selbst, und der holt seinen Wert
aus dem Netz — ein Provider-Abruf je Monat ist keine Aktion, die eedc von allein
auslöst ([[feedback_kein_grosser_heiler_knopf]]).

⛔ **Die Aktion füllt nur Lücken (P3b)** und nur die erreichbaren Monate. Die
Erreichbarkeit kommt aus Stufe 1 (Stundenmittel) und Stufe 2 (Tages-Min/Max) der
Vorrangkette — **ohne** die dritte, die das gepflegte Feld selbst ist; sonst
wäre es ein Kreislauf, und eine Prüfung mit Netzabruf hätte eine Nebenwirkung.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.monatsdaten import temperatur_aus_messung_uebernehmen
from backend.models import Anlage, Monatsdaten
from backend.models.tages_energie_profil import (
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.daten_checker import DatenChecker

JAHR = 2026
KAT = "wetterwert_fehlt"


async def _anlage(
    db,
    *,
    monate: dict[int, float | None],
    messreihe: dict[int, float] = None,
    per_minmax: dict[int, tuple[float, float]] = None,
) -> Anlage:
    """Anlage mit Monatszeilen; `messreihe`/`per_minmax` bauen die Tagesreihe.

    `monate`: Monat → gepflegte Ø-Temperatur (``None`` = die Lücke).
    `messreihe`: Monat → Stundenwert (Stufe 1) am 15. des Monats.
    `per_minmax`: Monat → (min, max) als Tages-Zusammenfassung (Stufe 2).
    """
    anlage = Anlage(anlagenname="N-426", leistung_kwp=10.0,
                    installationsdatum=date(JAHR, 1, 1))
    db.add(anlage)
    await db.flush()
    for monat, temp in monate.items():
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=JAHR, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=100.0,
            durchschnittstemperatur=temp,
        ))
    for monat, temp in (messreihe or {}).items():
        for stunde in (10, 11):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=date(JAHR, monat, 15),
                stunde=stunde, temperatur_c=temp,
            ))
    for monat, (tmin, tmax) in (per_minmax or {}).items():
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=date(JAHR, monat, 15),
            temperatur_min_c=tmin, temperatur_max_c=tmax,
        ))
    await db.commit()
    return anlage


async def _befunde(db, anlage_id: int):
    """Die Zeilen dieser Kategorie, die von der **Ø Temperatur** handeln.

    ⚠ **Warum hier gefiltert wird (29.09.2026, Paket „Die Wetterreihe
    geradeziehen").** Bis dahin trug `wetterwert_fehlt` genau ein Feld, und
    „eine Zeile in der Kategorie" hieß dasselbe wie „eine Zeile über die
    Ø Temperatur". Seit die Kategorie ihre ganze Klasse trägt — Strahlung,
    Sonnenstunden und die Einheitlichkeit der Quelle — stimmt diese Gleichung
    nicht mehr. **Die Substanz der Proben darunter ist unverändert:** sie
    prüfen die Temperatur-Zeile, und genau die kommen sie hier weiter.

    Gefiltert wird über das Feld, von dem die Zeile handelt. Die Proben dieser
    Datei prüfen ohnehin den vollen Meldungstext — ein Filter über denselben
    Text fügt keinen neuen Vertrag hinzu.
    """
    result = await DatenChecker(db).check_anlage(anlage_id)
    return [
        e for e in result.ergebnisse
        if e.kategorie == KAT and "Ø Temperatur" in e.meldung
    ]


async def _temperaturen(db, anlage_id: int) -> dict[int, float | None]:
    zeilen = (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.monat)
    )).scalars().all()
    return {md.monat: md.durchschnittstemperatur for md in zeilen}


# ═══ Klausel 1 — die Zählung n / m ══════════════════════════════════════════

@pytest.mark.asyncio
async def test_die_zeile_nennt_beide_zahlen(db):
    """Drei Monate leer, zwei davon erreichbar — genau die Fixture des Auftrags."""
    a = await _anlage(
        db,
        monate={1: None, 2: None, 3: None, 4: 12.5},
        messreihe={1: 3.0},
        per_minmax={2: (0.0, 8.0)},
    )
    befunde = await _befunde(db, a.id)

    assert len(befunde) == 1, [e.meldung for e in befunde]
    e = befunde[0]
    assert e.meldung == (
        "Ø Temperatur fehlt in 3 Monat(en), für 2 davon reicht die Messreihe"
    )
    assert e.schwere == "info"
    # Die betroffenen Monate stehen im Text — sonst wäre es eine Zahl ohne Fall.
    assert "01/2026" in e.details and "03/2026" in e.details
    # Der gepflegte Monat gehört nicht dazu.
    assert "04/2026" not in e.details


@pytest.mark.asyncio
async def test_die_aktion_nennt_nur_die_erreichbaren_monate(db):
    a = await _anlage(
        db,
        monate={1: None, 2: None, 3: None},
        messreihe={1: 3.0},
        per_minmax={2: (0.0, 8.0)},
    )
    e = (await _befunde(db, a.id))[0]

    assert e.action_kind == "temperatur_aus_messung"
    assert e.action_label == "Temperatur aus Messung übernehmen"
    assert e.action_params["anlage_id"] == a.id
    assert e.action_params["monate"] == ["01/2026", "02/2026"]


@pytest.mark.asyncio
async def test_ohne_erreichbare_monate_gibt_es_keinen_knopf(db):
    """Kein Heiler-Knopf, wo er nichts heilen kann — die Zeile sagt den Weg.

    ⛔ Ein Knopf, der „0 Monate nachgetragen" meldet, ist die P-6-Falle: ein
    Angebot, das niemand einlösen kann.
    """
    a = await _anlage(db, monate={1: None, 2: None})
    e = (await _befunde(db, a.id))[0]

    assert e.meldung == "Ø Temperatur fehlt in 2 Monat(en)"
    assert e.action_kind is None
    assert "Wetterdaten holen" in e.details


@pytest.mark.asyncio
async def test_alle_monate_gepflegt_ergibt_eine_ok_zeile(db):
    a = await _anlage(db, monate={1: 3.0, 2: 5.0})
    befunde = await _befunde(db, a.id)

    assert len(befunde) == 1
    assert befunde[0].schwere == "ok"
    assert befunde[0].action_kind is None


# ═══ Klausel 2 — die Aktion füllt genau die erreichbaren Lücken ═════════════

@pytest.mark.asyncio
async def test_die_aktion_fuellt_genau_die_zwei_erreichbaren(db):
    """Einzelwerte: 3,0 °C aus dem Stundenmittel, 4,0 °C aus Min/Max."""
    a = await _anlage(
        db,
        monate={1: None, 2: None, 3: None},
        messreihe={1: 3.0},
        per_minmax={2: (0.0, 8.0)},
    )

    ergebnis = await temperatur_aus_messung_uebernehmen(a.id, db)

    assert ergebnis["gefuellt"] == 2
    assert ergebnis["offen"] == 1
    werte = await _temperaturen(db, a.id)
    assert werte[1] == pytest.approx(3.0)
    assert werte[2] == pytest.approx(4.0)   # (0 + 8) / 2
    assert werte[3] is None                  # nicht erreichbar, bleibt leer


@pytest.mark.asyncio
async def test_ein_gepflegter_wert_bleibt_stehen(db):
    """**P3b — nur Lücken.** Auch dort, wo die Messreihe etwas anderes sagt.

    Der Monat trägt 12,5 °C von Hand; die Messreihe läge bei 3,0. Würde die
    Aktion überschreiben, ersetzte ein Reparatur-Knopf eine Anwender-Angabe —
    genau das, was eedc nicht tut.
    """
    a = await _anlage(db, monate={1: 12.5}, messreihe={1: 3.0})

    ergebnis = await temperatur_aus_messung_uebernehmen(a.id, db)

    assert ergebnis["gefuellt"] == 0
    assert (await _temperaturen(db, a.id))[1] == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_der_zweite_lauf_findet_nichts_mehr(db):
    """Idempotenz — sonst wäre der Knopf bei jedem Druck eine neue Änderung."""
    a = await _anlage(db, monate={1: None, 2: None}, messreihe={1: 3.0, 2: 5.0})

    erst = await temperatur_aus_messung_uebernehmen(a.id, db)
    zweit = await temperatur_aus_messung_uebernehmen(a.id, db)

    assert erst["gefuellt"] == 2
    assert zweit["gefuellt"] == 0
    werte = await _temperaturen(db, a.id)
    assert werte[1] == pytest.approx(3.0) and werte[2] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_nach_der_aktion_meldet_der_checker_die_restlichen(db):
    """Die Runde schließt sich: Knopf drücken ⇒ die Zeile wird kleiner."""
    a = await _anlage(
        db, monate={1: None, 2: None, 3: None}, messreihe={1: 3.0, 2: 5.0},
    )

    vorher = (await _befunde(db, a.id))[0]
    assert vorher.meldung == (
        "Ø Temperatur fehlt in 3 Monat(en), für 2 davon reicht die Messreihe"
    )

    await temperatur_aus_messung_uebernehmen(a.id, db)

    nachher = (await _befunde(db, a.id))[0]
    assert nachher.meldung == "Ø Temperatur fehlt in 1 Monat(en)"
    assert nachher.action_kind is None, (
        "Für den letzten Monat reicht die Reihe nicht — dann darf auch kein "
        "Knopf mehr dastehen."
    )


# ═══ Klausel 3 — kein Netzabruf, keine dritte Stufe ═════════════════════════

@pytest.mark.asyncio
async def test_ein_gepflegter_monat_macht_keinen_anderen_erreichbar(db):
    """Regressionsanker: Ein gepflegter Januar hilft dem leeren Februar nicht.

    ⚑ **Befund am Prüfstand, hier festgehalten:** Diese Probe ist **kein**
    Nachweis dafür, dass Stufe 3 ausgeschlossen ist — sie bliebe auch dann grün,
    wenn man ``gepflegt_je_monat`` mitgäbe (gemessen als Sprengsatz S-f2).
    Der Grund ist struktureller Art: Stufe 3 überspringt ``None``-Werte, und
    gefragt wird ausschließlich nach Monaten, deren Wert ``None`` ist — ein
    Kreislauf **kann** dort nicht entstehen. Was die Ausschluss-Regel wirklich
    hält, misst die Probe darunter am Aufruf selbst.
    """
    a = await _anlage(db, monate={1: 12.5, 2: None})

    befunde = await _befunde(db, a.id)
    assert befunde[0].meldung == "Ø Temperatur fehlt in 1 Monat(en)"
    assert befunde[0].action_kind is None

    ergebnis = await temperatur_aus_messung_uebernehmen(a.id, db)
    assert ergebnis["gefuellt"] == 0


@pytest.mark.asyncio
async def test_die_pruefung_fragt_die_kette_ohne_ihre_dritte_stufe(db, monkeypatch):
    """⛔ Der Vertrag am Aufruf: **kein** ``gepflegt_je_monat``, kein Netzabruf.

    Stufe 3 der Vorrangkette **ist** das Feld, um das es hier geht. Sie
    mitzugeben wäre ein Kreislauf — heute folgenlos (s. die Probe darüber), aber
    ein Vertrag, den niemand hält, ist keiner. Deshalb misst diese Probe den
    Aufruf statt seines Ergebnisses; sie ist die einzige Stelle, an der die
    Regel überhaupt rot werden kann.

    ⚠ Sie deckt zugleich die zweite Hälfte ab: `lade_monatsmittel_temperatur`
    liest ausschließlich die eigenen Tabellen. Eine Prüfung, die einen
    Wetter-Provider anfragt, hätte eine Nebenwirkung — und bei 34 leeren
    Monaten 34 davon.
    """
    from backend.services import mitteltemperatur as _mt
    import backend.services.daten_checker.monatsdaten as _dcm

    aufrufe: list[dict] = []
    echt = _mt.lade_monatsmittel_temperatur

    async def _spion(db_, anlage_id, gepflegt_je_monat=None, von=None, bis=None):
        aufrufe.append({"gepflegt": gepflegt_je_monat, "von": von, "bis": bis})
        return await echt(db_, anlage_id, gepflegt_je_monat, von, bis)

    monkeypatch.setattr(_mt, "lade_monatsmittel_temperatur", _spion)
    monkeypatch.setattr(_dcm, "lade_monatsmittel_temperatur", _spion, raising=False)

    a = await _anlage(db, monate={1: None, 2: None}, messreihe={1: 3.0})
    await _befunde(db, a.id)

    assert aufrufe, "Die Prüfung hat die Kette gar nicht gefragt — misst sie noch etwas?"
    assert all(x["gepflegt"] is None for x in aufrufe), (
        "Die Prüfung reicht die gepflegten Monatswerte in die Kette — das ist "
        f"Stufe 3 und damit das Feld selbst: {aufrufe}"
    )


@pytest.mark.asyncio
async def test_ohne_monatszeilen_schweigt_der_check(db):
    """Eine Anlage ohne erfassten Monat hat keine Wetter-Lücke, sondern gar nichts."""
    a = await _anlage(db, monate={})
    assert await _befunde(db, a.id) == []
