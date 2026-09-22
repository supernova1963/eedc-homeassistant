"""Der Zuordnungs-Schritt des Import-Wizards kennt nur die HEUTE laufenden Geräte
(Nachlese 4.0.50, A1).

**Dieselbe Klasse wie N-546**, nur eine Fläche weiter: `get_zuordnung_info` holte
**alle** Investitionen der Anlage ohne `aktiv` und ohne `stilllegungsdatum`. Ein
abgelöstes Zweitgerät wirkte dabei dreifach:

1. **`benoetigt_zuordnung`** — zwei Speicher „vorhanden" ⇒ der Wizard zeigte einen
   Schritt, den es fachlich nicht gibt (ein Gerät, 100 %).
2. **Die Zeile selbst** — das ausgebaute Gerät stand als ankreuzbare Zeile darin.
3. **Der Nenner der Default-Anteile** — `_anteil` teilt durch `Σ Kapazität` bzw.
   `Σ kWp`. Bei 12,8 kWh brutto laufend neben 5,06 kWh ausgebaut schlug der
   Wizard 71,7 / 28,3 vor; wer den Vorschlag übernahm, schrieb gut ein Viertel
   der importierten Speichermengen in die `InvestitionMonatsdaten` eines Geräts,
   das es nicht mehr gibt — und ebenso viel fehlte dem laufenden.
   (⚠ Die Bezugsgröße ist hier **brutto**, `get_inv_value("kapazitaet_kwh")` —
   die Nachbarsicht Sizing rechnet netto. Selbst gemessen, nicht angenommen.)

**Stichtag `date.today()`, nicht der Zeitraum des Imports** — und das ist gemessen,
nicht gewählt: die Route trägt nur `anlage_id` (kein Query-Parameter, kein Body),
und der Wizard ruft sie im Effekt auf `selectedAnlageId`, also **bevor** die
Vorschau die Perioden kennt (`DataImportWizard.tsx`). Damit dieselbe Wahl wie in
N-546 nebenan.

⚠ **Feste Daten, kein `date.today()` in dieser Probe** (`test_konformitaet_echte_uhr_in_tests.py`):
der Prüfling liest die Uhr selbst, ein Datum weit davor bzw. weit danach
entscheidet den Vergleich in Berlin, UTC und Auckland gleich.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.data_import import get_zuordnung_info
from backend.models import Anlage, Investition

STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)

#: Die Melder-Zahlen aus N-546 — damit beide Proben dieselbe Anlage beschreiben.
LAUFEND = {"kapazitaet_kwh": 12.8, "nutzbare_kapazitaet_kwh": 10.24}
ABGELOEST = {"kapazitaet_kwh": 5.06, "nutzbare_kapazitaet_kwh": 5.06}


async def _seed_speicher(db, *, aktiv: bool = True,
                         stillgelegt: date | None = None) -> int:
    anlage = Anlage(anlagenname="A1-Speicher", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher neu",
        anschaffungsdatum=date(2025, 6, 1), parameter=dict(LAUFEND),
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1), parameter=dict(ABGELOEST),
        aktiv=aktiv, stilllegungsdatum=stillgelegt,
    ))
    await db.commit()
    return anlage.id


async def _seed_pv(db, *, stillgelegt: date | None = None) -> int:
    anlage = Anlage(anlagenname="A1-PV", leistung_kwp=15.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2025, 6, 1), leistung_kwp=12.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Nord (abgebaut)",
        anschaffungsdatum=date(2015, 1, 1), leistung_kwp=3.0,
        stilllegungsdatum=stillgelegt,
    ))
    await db.commit()
    return anlage.id


# ── Speicher ────────────────────────────────────────────────────────────────


async def test_stillgelegter_speicher_erzwingt_keinen_zuordnungs_schritt(db):
    """Ein Gerät, kein Schritt, 100 % — die drei Wirkungen auf einmal."""
    anlage_id = await _seed_speicher(db, stillgelegt=STILLGELEGT_VERGANGENHEIT)

    info = await get_zuordnung_info(anlage_id, db=db)

    assert info.benoetigt_zuordnung is False, "zwei Zeilen wären ein Schritt ohne Frage"
    assert [s.bezeichnung for s in info.speicher] == ["Speicher neu"]
    assert info.speicher[0].default_anteil == 100.0, (
        "ungefiltert wären es 71,7 % — gut ein Viertel der Importmengen landete "
        "auf dem ausgebauten Gerät"
    )
    assert info.speicher[0].anteil_geschaetzt is False


async def test_abgewaehlter_speicher_ohne_datum_zaehlt_nicht(db):
    """`aktiv=False` = wie gelöscht — dieselbe Regel wie in `investition_filter`."""
    anlage_id = await _seed_speicher(db, aktiv=False)

    info = await get_zuordnung_info(anlage_id, db=db)

    assert info.benoetigt_zuordnung is False
    assert [s.bezeichnung for s in info.speicher] == ["Speicher neu"]
    assert info.speicher[0].default_anteil == 100.0


async def test_stilllegung_in_der_zukunft_zaehlt_heute_noch_mit(db):
    """Angekündigt ist nicht ausgebaut — sonst wäre der Filter ein Datumsfehler.

    Die Gegenrichtung belegt, dass der **Stichtag** gelesen wird und nicht bloß
    die Anwesenheit eines Datums. Brutto 12,8 / (12,8 + 5,06) = 71,7 %.
    """
    anlage_id = await _seed_speicher(db, stillgelegt=STILLGELEGT_ZUKUNFT)

    info = await get_zuordnung_info(anlage_id, db=db)

    assert info.benoetigt_zuordnung is True
    assert len(info.speicher) == 2
    anteile = {s.bezeichnung: s.default_anteil for s in info.speicher}
    assert anteile == {"Speicher neu": 71.7, "Speicher alt": 28.3}


# ── PV-Module (dieselbe Faltung, andere Bezugsgröße) ────────────────────────


async def test_stillgelegtes_pv_modul_faellt_aus_dem_kwp_nenner(db):
    anlage_id = await _seed_pv(db, stillgelegt=STILLGELEGT_VERGANGENHEIT)

    info = await get_zuordnung_info(anlage_id, db=db)

    assert info.benoetigt_zuordnung is False
    assert [m.bezeichnung for m in info.pv_module] == ["Dach Süd"]
    assert info.pv_module[0].default_anteil == 100.0, "ungefiltert wären es 80,0 %"
    assert info.pv_module[0].kwp == 12.0


async def test_pv_modul_mit_stilllegung_in_der_zukunft_bleibt(db):
    anlage_id = await _seed_pv(db, stillgelegt=STILLGELEGT_ZUKUNFT)

    info = await get_zuordnung_info(anlage_id, db=db)

    assert info.benoetigt_zuordnung is True
    anteile = {m.bezeichnung: m.default_anteil for m in info.pv_module}
    assert anteile == {"Dach Süd": 80.0, "Dach Nord (abgebaut)": 20.0}


# ── Wallbox / E-Auto (nur Liste und `benoetigt`) ────────────────────────────


async def test_stillgelegte_wallbox_und_eauto_verschwinden_aus_der_auswahl(db):
    """Hier gibt es keine Anteile — die Wirkung ist die Vorauswahl.

    Der Wizard setzt `wallboxId = info.wallboxen[0]?.id`. Stand das ausgebaute
    Gerät wegen seiner kleineren ID vorn, schrieb der Import die Ladedaten
    dorthin, ohne dass der Anwender etwas anklicken musste.
    """
    anlage = Anlage(anlagenname="A1-Verbraucher", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # ⚠ Das alte Gerät ZUERST — es bekommt damit die kleinere ID und stünde
    # ungefiltert an Position 0 der Vorauswahl.
    db.add(Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox alt",
        anschaffungsdatum=date(2015, 1, 1),
        stilllegungsdatum=STILLGELEGT_VERGANGENHEIT,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="E-Auto alt",
        anschaffungsdatum=date(2015, 1, 1),
        stilllegungsdatum=STILLGELEGT_VERGANGENHEIT,
    ))
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox neu",
        anschaffungsdatum=date(2025, 6, 1),
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="E-Auto neu",
        anschaffungsdatum=date(2025, 6, 1),
    ))
    await db.commit()

    info = await get_zuordnung_info(anlage.id, db=db)

    assert info.benoetigt_zuordnung is False
    assert [w.bezeichnung for w in info.wallboxen] == ["Wallbox neu"]
    assert [e.bezeichnung for e in info.eautos] == ["E-Auto neu"]
