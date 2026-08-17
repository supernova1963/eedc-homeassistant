"""Der Demo-Bestand muss BEIDE *Sonstiges*-Richtungen zeigen.

**Warum es diesen Prüfer gibt.** Bis zum 17.08.2026 kannte der Demo-Bestand
unter ``sonstiges`` **nur** einen Erzeuger (das Mini-BHKW). Das war keine
Geschmacksfrage, sondern eine Prüf-Blindstelle mit gemessener Folge:

* Ein *Sonstiges*-**Erzeuger** heißt in Registry und Snapshot **gleich**
  (``erzeugung_kwh``) — er war von **N-259** nie betroffen.
* Ein *Sonstiges*-**Verbraucher** heißt ``verbrauch_sonstig_kwh``, der
  Snapshot suchte aber nach dem Legacy-Zwilling ``verbrauch_kwh``. eedc hat
  damit ein MQTT-Topic **selbst publiziert und beim Einlesen verworfen**.

Weder die Demo noch die Anlage des Maintainers konnten den Fall zeigen —
gefunden hat ihn ein Anwender, und zwar erst Wochen später. Ein Bestand, der
nur die unproblematische Hälfte einer Entweder-Oder-Gruppe enthält, macht jede
Probe darauf blind.

**Was dieser Test NICHT leistet:** Er prüft den *Bestand*, nicht den Weg. Dass
der Tageswert am Ende ankommt, sichern die N-259-Proben; hier steht nur, dass
es überhaupt ein Gerät gibt, an dem sie greifen können.
"""

import pytest
from sqlalchemy import select

from backend.models.investition import Investition, InvestitionMonatsdaten

# Der kanonische Registry-Name. Der Legacy-Zwilling `verbrauch_kwh` bleibt
# lesbar (Altbestand im Mapping), darf aber in einem FRISCH erzeugten Bestand
# nicht auftauchen — sonst prüft die Demo genau den Namen, der das Problem war.
KANONISCH = "verbrauch_sonstig_kwh"
LEGACY = "verbrauch_kwh"


@pytest.mark.asyncio
async def test_demo_bestand_hat_sonstiges_verbraucher_und_erzeuger(db):
    """Beide Richtungen sind vertreten — sonst ist die Entweder-Oder-Gruppe halb."""
    from backend.api.routes.import_export.demo_data import create_demo_data

    await create_demo_data(db=db)

    rows = (
        await db.execute(
            select(Investition).where(Investition.typ == "sonstiges")
        )
    ).scalars().all()

    kategorien = {(inv.parameter or {}).get("kategorie") for inv in rows}
    assert "erzeuger" in kategorien, (
        "Der Demo-Bestand hat keinen Sonstiges-Erzeuger mehr — das Mini-BHKW "
        "ist die Referenz für den nie betroffenen Namensfall."
    )
    assert "verbraucher" in kategorien, (
        "Der Demo-Bestand hat KEINEN Sonstiges-Verbraucher. Genau diese Lücke "
        "hat N-259 wochenlang unsichtbar gehalten: Der Erzeuger heißt in "
        "Registry und Snapshot gleich, der Verbraucher nicht."
    )


@pytest.mark.asyncio
async def test_demo_verbraucher_nutzt_den_kanonischen_feldnamen(db):
    """Die Monatszeile trägt ``verbrauch_sonstig_kwh``, nicht den Legacy-Namen."""
    from backend.api.routes.import_export.demo_data import create_demo_data

    await create_demo_data(db=db)

    verbraucher = [
        inv
        for inv in (
            await db.execute(
                select(Investition).where(Investition.typ == "sonstiges")
            )
        ).scalars().all()
        if (inv.parameter or {}).get("kategorie") == "verbraucher"
    ]
    assert verbraucher, "kein Sonstiges-Verbraucher — siehe Test darüber"

    ids = {inv.id for inv in verbraucher}
    zeilen = [
        imd
        for imd in (
            await db.execute(select(InvestitionMonatsdaten))
        ).scalars().all()
        if imd.investition_id in ids
    ]
    assert zeilen, (
        "Der Sonstiges-Verbraucher hat keine Monatswerte — ohne sie zeigt "
        "weder die Monatstabelle noch die Spalte etwas an."
    )

    keys = {k for imd in zeilen for k in (imd.verbrauch_daten or {})}
    assert KANONISCH in keys, (
        f"Die Monatszeile trägt {KANONISCH!r} nicht. Das ist der Name, den die "
        "Zuordnungsfläche schreibt und unter dem eedc sein MQTT-Topic "
        "publiziert."
    )
    assert LEGACY not in keys, (
        f"Ein frisch erzeugter Bestand darf {LEGACY!r} nicht säen — der "
        "Legacy-Zwilling bleibt lesbar, aber wer ihn hier setzt, prüft "
        "ausgerechnet den Namen, der N-259 verursacht hat."
    )
