"""F-55 — der Rundlauf der personalisierten CSV-Vorlage muss geschlossen sein.

**Warum ein Rundlauf und nicht Export→Import.** Der Export ist heil: er liest
den Spaltennamen aus derselben Registry wie der Import. Ein Test auf
Export→Import ist deshalb grün, egal was die **Vorlage** baut — und genau dort
saß der Fehler. Bis v4.0.23 erzeugte `get_csv_template_info` seinen
Spaltennamen aus einer zweiten, handgepflegten Tabelle; drei Werte gingen beim
eigenen Rundlauf schweigend verloren (`erfolg: true, fehler: []`):

* Speicher/`ladung_netz_kwh` — die Tabelle führte den Key **zweimal**, der
  spätere (E-Auto-)Eintrag gewann ⇒ `_Ladung_Netz_kWh` statt `_Netzladung_kWh`
* *Sonstiges*/Erzeuger/`einspeise_erloes_euro` — roher Key statt Suffix
* *Sonstiges*/Verbrauchszähler/`zaehlerstand` — dito, und das ist der
  **einzige** Wert dieses Geräts (ausgeliefert mit v4.0.23, #377)

Der Wächter zeigt deshalb aufs richtige Objekt: **die Vorlage** (Angebot) gegen
**den Import** (Annahme), an den Routen, nicht am Layer.

Die Variantenmatrix deckt auch die einander ausschließenden Bedingungszweige
ab (`getrennte_strommessung` und sein `!`-Gegenstück, `arbitrage_faehig`,
`v2h_faehig`, `luft_luft` mit Innengeräten) — ein einzelnes Gerät je Typ
erreicht sie nicht, und ein nicht angebotenes Feld kann nicht verlorengehen.
"""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO

import pytest
from sqlalchemy import select

from backend.api.routes.import_export.csv_operations import (
    get_csv_template_info,
    import_csv,
)
from backend.core.field_definitions import get_felder_fuer_investition
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten

JAHR, MONAT = 2024, 3

#: Ein Gerät je Zeile. Die Bezeichnung ist der Spalten-Präfix und muss
#: eindeutig sein — zwei Varianten desselben Typs stehen nebeneinander.
GERAETE: list[tuple[str, str, dict]] = [
    ("pv-module", "StringSued", {"leistung_kwp": 5.0}),
    ("balkonkraftwerk", "BalkonNord", {"leistung_kwp": 0.8}),
    ("speicher", "SpeicherKeller", {"kapazitaet_kwh": 10.0, "arbitrage_faehig": True}),
    ("speicher", "SpeicherGarage", {"kapazitaet_kwh": 5.0}),
    ("waermepumpe", "WpKeller", {"wp_art": "luft_wasser", "getrennte_strommessung": True}),
    ("waermepumpe", "WpBad", {"wp_art": "luft_wasser"}),
    (
        "waermepumpe",
        "KlimaSplit",
        {
            "wp_art": "luft_luft",
            "innengeraete": [
                {"id": 1, "bezeichnung": "Wohnzimmer"},
                {"id": 3, "bezeichnung": "Schlafzimmer"},
            ],
        },
    ),
    ("e-auto", "EAutoZoe", {"v2h_faehig": True, "laedt_aus_netz": True}),
    ("wallbox", "WallboxHof", {}),
    ("sonstiges", "BhkwGarten", {"kategorie": "erzeuger"}),
    ("sonstiges", "PoolPumpe", {"kategorie": "verbraucher"}),
    ("sonstiges", "Gaszaehler", {"kategorie": "zaehler"}),
    ("sonstiges", "SpeicherSonst", {"kategorie": "speicher"}),
]

#: Ohne Wallbox — sonst verdrängt sie die E-Auto-Heimladung (N-302), und
#: `ladung_pv_kwh`/`ladung_netz_kwh` des E-Autos fehlen in beiden Listen.
GERAETE_OHNE_WALLBOX = [g for g in GERAETE if g[0] != "wallbox"]


async def _baue_anlage(db, geraete) -> tuple[int, list[Investition]]:
    anlage = Anlage(
        anlagenname="Rundlauf",
        leistung_kwp=5.8,
        installationsdatum=date(JAHR - 1, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    invs = []
    for typ, bez, params in geraete:
        inv = Investition(
            anlage_id=anlage.id,
            typ=typ,
            bezeichnung=bez,
            anschaffungsdatum=date(JAHR - 1, 1, 1),
            anschaffungskosten_gesamt=1000.0,
            aktiv=True,
            parameter=dict(params),
        )
        db.add(inv)
        invs.append(inv)
    await db.flush()
    await db.commit()
    return anlage.id, invs


class _FakeUpload:
    """Minimales `UploadFile`-Double — die Route nutzt nur `await .read()`."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


def _fuellwert(spalte: str, lfd: int) -> str:
    """Je Spalte ein **eindeutiger** Wert — sonst deckt ein Vertauschen zweier
    Spalten nichts auf (die Zahl stünde am falschen Feld und der Test wäre
    trotzdem grün)."""
    if spalte == "Jahr":
        return str(JAHR)
    if spalte == "Monat":
        return str(MONAT)
    if spalte == "Notizen" or spalte.endswith("_Sonderkosten_Notiz"):
        return ""
    return str(100 + lfd)


async def _rundlauf(db, geraete) -> tuple[dict[str, str], dict[int, dict]]:
    """Vorlage bauen → jede Spalte füllen → importieren → IMD zurücklesen.

    Gibt zurück: *was in welche Spalte geschrieben wurde* und *was danach in
    den IMD-Zeilen steht*. Der Vergleich der beiden ist die Probe.
    """
    anlage_id, _ = await _baue_anlage(db, geraete)
    vorlage = await get_csv_template_info(anlage_id, db)

    out = StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(vorlage.spalten)
    writer.writerow([_fuellwert(s, i) for i, s in enumerate(vorlage.spalten)])

    ergebnis = await import_csv(
        anlage_id=anlage_id,
        file=_FakeUpload(out.getvalue()),
        ueberschreiben=True,
        auto_wetter=False,
        db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler
    assert not ergebnis.fehler, ergebnis.fehler

    imds = (
        await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.jahr == JAHR,
                InvestitionMonatsdaten.monat == MONAT,
            )
        )
    ).scalars().all()
    return {s: _fuellwert(s, i) for i, s in enumerate(vorlage.spalten)}, {
        imd.investition_id: (imd.verbrauch_daten or {}) for imd in imds
    }


@pytest.mark.asyncio
async def test_jeder_angebotene_wert_kommt_an(db):
    """Der Rundlauf ist geschlossen: was die Vorlage anbietet, nimmt der Import an.

    Das ist die Probe, die es nie gab. Sie deckt alle drei F-55-Fälle ab und
    jede künftige Namens-Drift zwischen Vorlage und Registry — auch an einem
    Feld, das es heute noch nicht gibt.
    """
    geschrieben, imd_je_inv = await _rundlauf(db, GERAETE_OHNE_WALLBOX)
    alle = list((await db.execute(select(Investition))).scalars().all())

    fehlend: list[str] = []
    geprueft = 0
    for inv in alle:
        felder = get_felder_fuer_investition(
            inv.typ, inv.parameter, anlage_investitionen=alle
        )
        daten = imd_je_inv.get(inv.id, {})
        for feld_def in felder:
            feld = feld_def["feld"]
            spalte = f"{inv.bezeichnung}_{feld_def.get('csv_suffix', feld)}"
            if spalte not in geschrieben:
                fehlend.append(f"{inv.typ}/{inv.bezeichnung}: Spalte fehlt — {spalte}")
                continue
            geprueft += 1
            ist = daten.get(feld)
            if ist is None:
                fehlend.append(
                    f"{inv.typ}/{inv.bezeichnung}: Spalte '{spalte}' angeboten, "
                    f"Feld '{feld}' nach dem Import leer"
                )
            elif float(ist) != float(geschrieben[spalte]):
                # Jede Spalte trägt einen eigenen Wert — steht hier ein anderer,
                # ist er über den falschen Feld-Key gelandet.
                fehlend.append(
                    f"{inv.typ}/{inv.bezeichnung}: '{spalte}' trug "
                    f"{geschrieben[spalte]}, '{feld}' hält {ist}"
                )

    assert not fehlend, "Der Rundlauf verliert oder verwechselt Werte:\n  " + "\n  ".join(fehlend)
    # Ohne diese Zeile wäre der Test auch dann grün, wenn die Vorlage gar
    # nichts mehr anbietet (leere Schleife = keine Beanstandung).
    assert geprueft >= 40, f"zu wenige Felder im Rundlauf geprüft: {geprueft}"


@pytest.mark.asyncio
async def test_drei_f55_faelle_namentlich(db):
    """Die drei ausgelieferten Fälle einzeln — als Regression mit Namen.

    Der Test oben fängt sie baumweit; dieser hier hält fest, **welche** Spalte
    sie tragen, damit ein Umbenennen in der Registry nicht unbemerkt an einem
    Melder-Fall vorbeigeht (#377 hängt am Zählerstand).
    """
    geschrieben, imd_je_inv = await _rundlauf(db, GERAETE_OHNE_WALLBOX)
    invs = {i.bezeichnung: i for i in (await db.execute(select(Investition))).scalars()}

    erwartet = [
        ("SpeicherKeller", "SpeicherKeller_Netzladung_kWh", "ladung_netz_kwh"),
        ("BhkwGarten", "BhkwGarten_Einspeise_Erloes_Euro", "einspeise_erloes_euro"),
        ("Gaszaehler", "Gaszaehler_Zaehlerstand", "zaehlerstand"),
    ]
    for bez, spalte, feld in erwartet:
        assert spalte in geschrieben, f"Vorlage bietet '{spalte}' nicht an"
        daten = imd_je_inv.get(invs[bez].id, {})
        assert daten.get(feld) is not None, f"'{spalte}' kam nicht als '{feld}' an"
        assert float(daten[feld]) == float(geschrieben[spalte])


@pytest.mark.asyncio
async def test_n302_wallbox_verdraengt_eauto_heimladung_auch_in_der_vorlage(db):
    """N-302 — die Vorlage bietet an, was der Monatsabschluss auch anbietet.

    Existiert eine Wallbox, ist sie die kanonische Heimladungs-Quelle
    (`get_emob_heimladung_canonical`) und `bedingung_anlage: keine_wallbox`
    blendet `ladung_pv_kwh`/`ladung_netz_kwh` am E-Auto aus. Die Vorlage rief
    `get_felder_fuer_investition` **ohne** `anlage_investitionen` und bot die
    Spalten trotzdem an — ein Angebot, das die Oberfläche daneben zurücknimmt.

    Der **Import** nimmt sie weiterhin an: er darf nie still etwas wegwerfen
    (das ist die F-55-Lehre und der Vertrag von
    `get_alle_felder_fuer_investition`). Geprüft wird deshalb nur das Angebot.
    """
    anlage_id, _ = await _baue_anlage(db, GERAETE)          # MIT Wallbox
    mit_wb = set((await get_csv_template_info(anlage_id, db)).spalten)
    assert "EAutoZoe_Ladung_PV_kWh" not in mit_wb
    assert "EAutoZoe_Ladung_Netz_kWh" not in mit_wb
    # Die Heimladung verschwindet nicht — sie steht an der Wallbox, dort ist
    # sie die kanonische Quelle. Und was am E-Auto NICHT verdrängt ist (externe
    # Ladung, km, V2H), bleibt selbstverständlich erfassbar.
    assert "WallboxHof_Ladung_kWh" in mit_wb
    assert "WallboxHof_Ladung_PV_kWh" in mit_wb
    assert "EAutoZoe_Ladung_Extern_kWh" in mit_wb
    assert "EAutoZoe_V2H_kWh" in mit_wb


@pytest.mark.asyncio
async def test_n302_ohne_wallbox_bleibt_die_aufteilung_angeboten(db):
    """Die Gegenrichtung: ohne Wallbox ist das E-Auto die Quelle.

    Ohne diese Hälfte wäre der Test oben auch dann grün, wenn die Vorlage die
    beiden Spalten **nie** mehr anbietet — und damit ein Anwender ohne Wallbox
    seine PV/Netz-Aufteilung per CSV nicht mehr liefern könnte.
    """
    anlage_id, _ = await _baue_anlage(db, GERAETE_OHNE_WALLBOX)
    ohne_wb = set((await get_csv_template_info(anlage_id, db)).spalten)
    assert "EAutoZoe_Ladung_PV_kWh" in ohne_wb
    assert "EAutoZoe_Ladung_Netz_kWh" in ohne_wb
