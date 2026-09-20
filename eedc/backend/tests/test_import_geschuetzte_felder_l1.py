"""Was der Import NICHT überschreibt, zählt er — und sagt es (Schutz-Mechanik).

Schwestern: `test_import_ueberschreiben_haken_349.py` (der Haken, der die
Hierarchie durchbricht — die Gegenrichtung zu dieser Datei),
`test_import_ziel_investition_349.py` und `test_import_hauszaehler_349.py`
(der gerätegebundene Weg, in dem der Schutz hier greift).

**Warum es diese Datei gibt.** `apply_import` führt seit Etappe 3d Päckchen 2
zwei Antwortfelder, `geschuetzt_count` und `geschuetzte_felder`, und baut daraus
den Wizard-Hinweis „X Felder wurden durch manuell gepflegte Werte geschützt".
Die Buchführung dahinter steht **dreimal** in derselben Funktion (Sammler für
die Gerätewerte, Hauszähler-Zweig, Top-Level-Schreibblock) — und war **von
keiner Probe und keinem Golden-Master-Schritt berührt**: baumweit assertierte
kein Test `geschuetzt_count`, und die drei Demo-Datenbanken des Golden Master
tragen **keinen einzigen** Wert mit `manual:*`-Provenance (gemessen 19.09.2026,
`select count(*) … where source_provenance like '%manual%'` = 0 in
`monatsdaten` *und* `investition_monatsdaten`). Ein Wert ohne manuelle Herkunft
kann nie abgewiesen werden — die Zeilen liefen also nie.

**Was der Import mit Handarbeit macht, ist an drei Stellen verschieden — und
das ist gemessen, nicht angenommen** (20.09.2026). Alle drei stehen unten, weil
nur die erste den Zähler bewegt und die beiden anderen trotzdem Handarbeit
bewahren:

| Weg | ohne Haken | `geschuetzt_count` |
| --- | --- | --- |
| **gerätegebunden**, Hauszähler-Feld (N-229) | Hierarchie weist ab | **+1** |
| anlagenweit, Gerätewert (`InvestitionMonatsdaten`) | Sub-Key wird übersprungen (`skipped_existing`, `import_writer.py`) — die Hierarchie wird gar nicht gefragt | 0 |
| anlagenweit, Feld der Monatszeile | der ganze Monat wird übersprungen, **bevor** geschrieben wird | 0 |

⚠ **Die Zahl zählt abgewiesene Schreibvorgänge, nicht bewahrte Werte.** Wer den
Monats-Skip des anlagenweiten Weges oder den Sub-Key-Skip im `import_writer`
anfasst, ändert damit auch diese Zahl — und den Hinweistext, den der Anwender
sieht. Deshalb hält diese Datei alle drei Lagen fest und nicht nur die eine,
die zählt.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.api.routes.data_import import (
    ApplyMonthInput,
    ApplyRequest,
    apply_import,
)
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.provenance import write_with_provenance
from backend.tests import factories

JAHR, MONAT = 2025, 6


async def _monatszeile_mit_handarbeit(
    db, anlage_id: int, *, einspeisung: float = 700.0, netzbezug: float = 310.0
) -> Monatsdaten:
    """Eine Monatszeile, deren `einspeisung_kwh` von Hand gepflegt wurde.

    Die Provenance entsteht über denselben Schreibweg wie im Formular
    (`write_with_provenance` mit `manual:form`) — ein von Hand gesetztes
    `source_provenance`-Dict wäre eine Behauptung über den Schreibweg statt
    seiner Benutzung. `netzbezug_kwh` bleibt bewusst ohne Provenance: an ihm
    wird sichtbar, dass nur das geschützte Feld stehen bleibt.
    """
    md = Monatsdaten(
        anlage_id=anlage_id, jahr=JAHR, monat=MONAT, netzbezug_kwh=netzbezug
    )
    db.add(md)
    await db.flush()
    await write_with_provenance(
        db, md, "einspeisung_kwh", einspeisung,
        source="manual:form", writer="alice",
    )
    await db.flush()
    assert md.source_provenance["einspeisung_kwh"]["source"] == "manual:form"
    return md


async def _anlage_mit_modul_und_geraetewert(db):
    """Anlage, ein PV-Modul, ein von Hand gepflegter Gerätewert — keine Monatszeile."""
    a = await factories.anlage(db, anlagenname="Handarbeit L1")
    modul = await factories.investition(
        db, a.id, "pv-module", bezeichnung="String Süd",
        anschaffungsdatum=date(2023, 1, 1), leistung_kwp=10.0,
    )
    db.add(InvestitionMonatsdaten(
        investition_id=modul.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"pv_erzeugung_kwh": 900.0},
        source_provenance={
            "verbrauch_daten.pv_erzeugung_kwh": {
                "source": "manual:form", "writer": "alice",
                "written_at": "2025-07-01T00:00:00",
            }
        },
    ))
    await db.commit()
    return a, modul


async def _pv_wert(db, investition_id: int):
    row = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == investition_id,
            InvestitionMonatsdaten.jahr == JAHR,
            InvestitionMonatsdaten.monat == MONAT,
        )
    )).scalar_one()
    return (row.verbrauch_daten or {}).get("pv_erzeugung_kwh")


# ═══════════════════════════════════════════════════════════════════════════
# Der Zweig, der zählt: Hauszähler-Felder im gerätegebundenen Weg (N-229)
# ═══════════════════════════════════════════════════════════════════════════


async def test_ziel_zweig_schuetzt_manuellen_hauszaehler_wert(db):
    """Der Stationsimport meldet denselben Zähler — der Wert von Hand bleibt.

    Der gerätegebundene Weg kennt **keinen** Monats-Skip (#349): er erreicht den
    Schreibblock auch ohne Haken, und genau dort muss die Hierarchie greifen.
    Das ist die einzige Stelle des ganzen Endpunkts, an der `geschuetzt_count`
    heute über 0 geht.
    """
    ids = await factories.zwei_wechselrichter(db)
    md = await _monatszeile_mit_handarbeit(db, ids["anlage"])
    await db.commit()

    antwort = await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(
            monate=[ApplyMonthInput(
                jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=500.0,
                einspeisung_kwh=700.0, netzbezug_kwh=311.0,
            )],
            ziel_investition_id=ids["Sofar 2200"]["wr"],
        ),
        ueberschreiben=False, datenquelle="cloud_import", db=db,
    )
    await db.commit()

    assert antwort.geschuetzt_count == 1
    assert antwort.geschuetzte_felder == ["einspeisung_kwh"]
    await db.refresh(md)
    assert md.einspeisung_kwh == 700.0, "Handarbeit wurde überschrieben"
    assert md.netzbezug_kwh == 311.0, (
        "Nur das geschützte Feld bleibt stehen — der Rest der Station kommt an."
    )
    assert antwort.warnungen[0].startswith(
        "1 Felder wurden durch manuell gepflegte Werte geschützt"
    ), antwort.warnungen


async def test_ziel_zweig_mit_haken_ersetzt_den_handwert(db):
    """Gegenprobe im selben Zweig: der Haken IST die Anordnung des Anwenders —
    dann gibt es nichts zu schützen und nichts zu melden."""
    ids = await factories.zwei_wechselrichter(db)
    md = await _monatszeile_mit_handarbeit(db, ids["anlage"])
    await db.commit()

    antwort = await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(
            monate=[ApplyMonthInput(
                jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=500.0,
                einspeisung_kwh=800.0, netzbezug_kwh=311.0,
            )],
            ziel_investition_id=ids["Sofar 2200"]["wr"],
        ),
        ueberschreiben=True, datenquelle="cloud_import", db=db,
    )
    await db.commit()

    assert antwort.geschuetzt_count == 0
    assert antwort.geschuetzte_felder == []
    assert not any("geschützt" in w for w in antwort.warnungen)
    await db.refresh(md)
    assert md.einspeisung_kwh == 800.0


# ═══════════════════════════════════════════════════════════════════════════
# Gerätewerte — Handarbeit bleibt, der Zähler bewegt sich nicht
# ═══════════════════════════════════════════════════════════════════════════


async def test_geraetewert_von_hand_bleibt_ohne_haken_stehen(db):
    """Ohne Haken überlebt der gepflegte Modulwert — **ungezählt**.

    Der `import_writer` überspringt einen vorhandenen Sub-Key, bevor die
    Hierarchie überhaupt gefragt wird (`skipped_existing`); abgewiesen hat
    niemand etwas, also zählt auch nichts. Der Wizard-Hinweis schweigt hier
    bewusst — und wer den Skip anfasst, macht ihn sprechen.
    """
    a, modul = await _anlage_mit_modul_und_geraetewert(db)

    antwort = await apply_import(
        anlage_id=a.id,
        data=ApplyRequest(monate=[ApplyMonthInput(
            jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=1234.0, netzbezug_kwh=450.0,
        )]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )
    await db.commit()

    assert antwort.geschuetzt_count == 0
    assert antwort.geschuetzte_felder == []
    assert await _pv_wert(db, modul.id) == 900.0, "Handarbeit wurde überschrieben"


async def test_geraetewert_mit_haken_wird_ersetzt(db):
    """Gegenprobe: mit Haken kommt der Import durch — Ollis Ablauf (#349)."""
    a, modul = await _anlage_mit_modul_und_geraetewert(db)

    antwort = await apply_import(
        anlage_id=a.id,
        data=ApplyRequest(monate=[ApplyMonthInput(
            jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=1234.0, netzbezug_kwh=450.0,
        )]),
        ueberschreiben=True, datenquelle="portal_import", db=db,
    )
    await db.commit()

    assert antwort.geschuetzt_count == 0
    assert await _pv_wert(db, modul.id) == 1234.0


# ═══════════════════════════════════════════════════════════════════════════
# Der anlagenweite Weg — der Monat fällt aus, bevor geschrieben wird
# ═══════════════════════════════════════════════════════════════════════════


async def test_anlagenweit_ueberspringt_den_monat_statt_zu_schuetzen(db):
    """Ohne Haken schützt der anlagenweite Weg das Feld nicht — er lässt den
    ganzen Monat aus, und meldet ihn als übersprungen statt als geschützt.

    Festgehalten, weil die Zahl sonst missverstanden wird: `geschuetzt_count`
    ist **0** und der Handwert steht trotzdem noch. Fiele der Monats-Skip
    (er ist der Grund, aus dem der gerätegebundene Weg überhaupt entstand),
    liefe derselbe Fall in den Schreibblock — dann zählte er.
    """
    a = await factories.anlage(db, anlagenname="Handarbeit anlagenweit")
    md = await _monatszeile_mit_handarbeit(db, a.id)
    await db.commit()

    antwort = await apply_import(
        anlage_id=a.id,
        data=ApplyRequest(monate=[ApplyMonthInput(
            jahr=JAHR, monat=MONAT, einspeisung_kwh=999.0, netzbezug_kwh=450.0,
        )]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )
    await db.commit()

    assert (antwort.importiert, antwort.uebersprungen) == (0, 1)
    assert antwort.geschuetzt_count == 0
    await db.refresh(md)
    assert md.einspeisung_kwh == 700.0
    assert md.netzbezug_kwh == 310.0


async def test_anlagenweit_mit_haken_ersetzt_und_zaehlt_nichts(db):
    """Gegenprobe: mit Haken wird die Handarbeit ersetzt (`benutzer_override`)
    — auch das zählt nicht als geschützt, sonst widerspräche der Hinweis dem
    Haken (genau der Vorwurf aus #349)."""
    a = await factories.anlage(db, anlagenname="Handarbeit anlagenweit mit Haken")
    md = await _monatszeile_mit_handarbeit(db, a.id)
    await db.commit()

    antwort = await apply_import(
        anlage_id=a.id,
        data=ApplyRequest(monate=[ApplyMonthInput(
            jahr=JAHR, monat=MONAT, einspeisung_kwh=999.0, netzbezug_kwh=450.0,
        )]),
        ueberschreiben=True, datenquelle="portal_import", db=db,
    )
    await db.commit()

    assert (antwort.importiert, antwort.uebersprungen) == (1, 0)
    assert antwort.geschuetzt_count == 0
    assert not any("geschützt" in w for w in antwort.warnungen)
    await db.refresh(md)
    assert md.einspeisung_kwh == 999.0
