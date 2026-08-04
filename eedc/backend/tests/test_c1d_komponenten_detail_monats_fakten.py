"""C1d — der Komponenten-Detailblock der Monatsroute kommt aus den Fakten (P10).

Letzte Etappe des P10-Strangs: bis hierher faltete `get_aktueller_monat` neben
der Quellen-Kaskade **eine eigene** `InvestitionMonatsdaten`-Batch, aus der
Speicher-Netzladung, WP-Heiz-/Warmwasser-Split, eMob Netz/Extern/V2H,
BKW-Eigenverbrauch und die sechs Sonstiges-Mengen entstanden. Sie war die
letzte anlagenweite Faltung des Baums (N-107) — und sie hatte zwei Fehler, die
die Schicht nicht hat. Beide sind hier festgehalten:

* **E-Auto und Wallbox wurden roh addiert.** Beide messen denselben Fluss aus
  zwei Perspektiven (Vehicle vs. Loadpoint); wo beide gepflegt sind, stand die
  Netzladung doppelt — in der Kachel *Cockpit → Monat*, im **T-Konto** (dort
  × Arbeitspreis, also geldwirksam) und in der Jahressumme. Am Demo-Bestand
  waren das über 25 Monate **5.976 statt 3.831 kWh (+56 %)**. Der Rest des
  Baums vermeidet die Doppelzählung längst über den kanonischen Pool (#262);
  `typ_aggregation` derselben Route nennt den Grund sogar im Kommentar.
* **Kein Laufzeit-Filter.** Die Batch nahm jede IMD-Zeile ihres Typs, auch aus
  Monaten **vor der Anschaffung** — die #236-Klasse, die alle anderen
  Read-Sites seit v3.29 hinter sich haben. Am Demo-Bestand trug die Route vier
  Monate lang Wärme einer Wärmepumpe, die es noch nicht gab (3.400 kWh davon
  im Jahresaggregat 2024).

Die vier Sonstiges-Mengen, die der Schicht dafür fehlten (Eigenverbrauch,
Einspeisung, Bezug PV, Bezug Netz), sind additiv nachgezogen — samt
`je_geraet`, damit auch die Pro-Gerät-Darstellung nicht mehr selbst faltet.
Sie sind **kategorie-bewusst** aufgelöst wie Erzeugung/Verbrauch: ein Erzeuger
trägt keinen Netzbezug, ein Verbraucher speist nicht ein.

Geschwister-Dateien: `test_c1b_komponenten_monats_fakten.py`,
`test_c1c_aktueller_monat_monats_fakten.py`, `test_monats_fakten_schicht.py`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten

JAHR, MONAT = 2025, 3


async def _anlage(db: AsyncSession, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=0.0, einspeisung_kwh=0.0))
    return anlage


async def _inv(db, anlage, typ, *, vd=None, anschaffung=date(2023, 1, 1),
               parameter=None, jahr=JAHR, monat=MONAT, bezeichnung=None) -> int:
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=bezeichnung or f"{typ}-Test",
        anschaffungsdatum=anschaffung, parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    if vd is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=jahr,
                                      monat=monat, verbrauch_daten=vd))
    return inv.id


# ───────────────────────── Befund 1: Pool statt Roh-Summe ────────────────────


async def test_emob_netzanteil_zaehlt_eauto_und_wallbox_nicht_doppelt(db):
    """E-Auto UND Wallbox gepflegt ⇒ EIN Netzanteil, nicht die Summe beider.

    Beide Zeilen beschreiben denselben Ladevorgang. Die Roh-Summe der
    Vorfassung ergab hier **100 kWh** (50 + 50) für einen Fluss, der 50 kWh
    aus dem Netz gezogen hat.
    """
    anlage = await _anlage(db, "emob-pool")
    await _inv(db, anlage, "e-auto",
               vd={"ladung_kwh": 124.0, "ladung_pv_kwh": 74.0, "ladung_netz_kwh": 50.0})
    await _inv(db, anlage, "wallbox",
               vd={"ladung_kwh": 124.0, "ladung_pv_kwh": 74.0, "ladevorgaenge": 4})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.emob_ladung_netz_kwh == 50.0
    # Gegenprobe: die Zahl stammt aus derselben Trias wie der PV-Anteil daneben.
    fakten = await lade_monats_fakten(db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    assert res.emob_ladung_netz_kwh == round(fakten[0].emob.ladung_netz_kwh, 2)


async def test_emob_quellenwahl_ist_strukturell_nicht_magnitudenabhaengig(db):
    """Die Wallbox ist Quelle, weil sie existiert — nicht weil sie größer ist.

    Hier trägt die E-Auto-Zeile den **größeren** Netzanteil (300 gegen 50).
    Ein Magnituden-Pool nähme sie; der Kanon nimmt trotzdem die Wallbox
    (KONZEPT-WALLBOX-EAUTO Entscheidung 1 — #262 junky84 hatte 3.300 kWh
    Streudaten auf der E-Auto-IMD). Dieser Test hält fest, dass die Route
    dieselbe Regel erbt wie ROI, Aussichten, HA-Export und Vorjahresvergleich,
    statt sich eine eigene zu bauen.
    """
    anlage = await _anlage(db, "emob-quellenwahl")
    await _inv(db, anlage, "e-auto",
               vd={"ladung_kwh": 400.0, "ladung_pv_kwh": 100.0, "ladung_netz_kwh": 300.0})
    await _inv(db, anlage, "wallbox",
               vd={"ladung_kwh": 124.0, "ladung_pv_kwh": 74.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.emob_ladung_netz_kwh == 50.0


async def test_emob_netzanteil_ohne_wallbox_unveraendert(db):
    """Gegenprobe: ohne zweite Quelle gibt es nichts zu poolen.

    Absichtlich auch gegen die Vorfassung grün — sie hält fest, dass der
    Pool den Normalfall NICHT verschiebt (sonst wäre die Korrektur oben nur
    eine andere Konstante).
    """
    anlage = await _anlage(db, "emob-solo")
    await _inv(db, anlage, "e-auto",
               vd={"ladung_kwh": 205.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 55.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.emob_ladung_netz_kwh == 55.0


# ─────────────────────── Befund 2: Laufzeit-Filter (#236) ────────────────────


async def test_wp_vor_der_anschaffung_traegt_keine_waerme(db):
    """Eine IMD-Zeile aus einem Monat vor der Anschaffung zählt nicht.

    Der Fall ist real: Import und Nachpflege schreiben Zeilen, ohne das
    Anschaffungsdatum zu prüfen. Bis C1d zeigte die Route dafür Heizwärme
    einer Wärmepumpe, die im Monat noch nicht existierte — und
    `JahrAggregat` summierte sie ins Jahr.
    """
    anlage = await _anlage(db, "wp-vor-anschaffung")
    await _inv(db, anlage, "waermepumpe",
               anschaffung=date(2025, 6, 1),  # NACH dem Berichtsmonat
               vd={"heizenergie_kwh": 960.0, "warmwasser_kwh": 100.0,
                   "strom_heizen_kwh": 211.4, "strom_warmwasser_kwh": 28.6},
               parameter={"getrennte_strommessung": True})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.wp_heizung_kwh is None
    assert res.wp_warmwasser_kwh is None
    assert res.wp_strom_heizen_kwh is None
    assert res.wp_strom_warmwasser_kwh is None


async def test_wp_nach_stilllegung_traegt_keine_waerme(db):
    """Dieselbe Grenze am anderen Ende — die Stilllegung.

    Nicht dieselbe Assertion mit anderem Datum: Anschaffung und Stilllegung
    sind zwei Felder und wurden in #236/#239 getrennt nachgezogen.
    """
    anlage = await _anlage(db, "wp-nach-stilllegung")
    inv_id = await _inv(db, anlage, "waermepumpe",
                        anschaffung=date(2023, 1, 1),
                        vd={"heizenergie_kwh": 500.0, "warmwasser_kwh": 60.0})
    inv = await db.get(Investition, inv_id)
    inv.stilllegungsdatum = date(2024, 12, 31)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.wp_heizung_kwh is None
    assert res.wp_warmwasser_kwh is None


async def test_wp_innerhalb_der_laufzeit_unveraendert(db):
    """Gegenprobe zu den beiden Grenzen — im Laufzeitfenster zählt alles."""
    anlage = await _anlage(db, "wp-aktiv")
    await _inv(db, anlage, "waermepumpe",
               vd={"heizenergie_kwh": 960.0, "warmwasser_kwh": 100.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.wp_heizung_kwh == 960.0
    assert res.wp_warmwasser_kwh == 100.0


# ────────────────── Sonstiges: vier neue Mengen, kategorie-bewusst ───────────


async def test_sonstiges_erzeuger_traegt_keinen_netzbezug(db):
    """Ein Erzeuger mit Bezugs-Keys in der Zeile trägt sie NICHT.

    Die Kategorie entscheidet, welche Größen eine Sonstiges-Zeile überhaupt
    behaupten darf — dieselbe Regel, die Erzeugung/Verbrauch seit jeher
    trennt. Bis C1d las die Route beide Seiten roh und ohne Kategorie.
    """
    anlage = await _anlage(db, "sonstiges-erzeuger")
    await _inv(db, anlage, "sonstiges", bezeichnung="Mini-BHKW",
               parameter={"kategorie": "erzeuger"},
               vd={"erzeugung_kwh": 400.0, "eigenverbrauch_kwh": 300.0,
                   "einspeisung_kwh": 100.0,
                   # gehört nicht zum Erzeuger und darf nicht durchschlagen:
                   "bezug_netz_kwh": 77.0, "bezug_pv_kwh": 33.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.sonstiges_erzeugung_kwh == 400.0
    assert res.sonstiges_eigenverbrauch_kwh == 300.0
    assert res.sonstiges_einspeisung_kwh == 100.0
    assert res.sonstiges_bezug_netz_kwh is None
    assert res.sonstiges_bezug_pv_kwh is None


async def test_sonstiges_verbraucher_speist_nicht_ein(db):
    """Die Gegenrichtung derselben Regel."""
    anlage = await _anlage(db, "sonstiges-verbraucher")
    await _inv(db, anlage, "sonstiges", bezeichnung="Heizstab",
               parameter={"kategorie": "verbraucher"},
               vd={"verbrauch_sonstig_kwh": 120.0, "bezug_pv_kwh": 90.0,
                   "bezug_netz_kwh": 30.0,
                   # gehört nicht zum Verbraucher:
                   "einspeisung_kwh": 55.0, "eigenverbrauch_kwh": 44.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.sonstiges_verbrauch_kwh == 120.0
    assert res.sonstiges_bezug_pv_kwh == 90.0
    assert res.sonstiges_bezug_netz_kwh == 30.0
    assert res.sonstiges_einspeisung_kwh is None
    assert res.sonstiges_eigenverbrauch_kwh is None


async def test_sonstiges_geraete_liste_kommt_aus_je_geraet(db):
    """Die Pro-Gerät-Darstellung faltet nicht mehr selbst.

    Sie liest `SonstigesFakten.je_geraet` — und erbt damit den
    Laufzeit-Filter: ein Gerät außerhalb seiner Laufzeit taucht gar nicht
    erst auf, statt mit einer Zeile aus einem fremden Monat.
    """
    anlage = await _anlage(db, "sonstiges-geraete")
    await _inv(db, anlage, "sonstiges", bezeichnung="BHKW",
               parameter={"kategorie": "erzeuger"},
               vd={"erzeugung_kwh": 400.0, "eigenverbrauch_kwh": 300.0,
                   "einspeisung_kwh": 100.0})
    await _inv(db, anlage, "sonstiges", bezeichnung="Heizstab",
               parameter={"kategorie": "verbraucher"},
               vd={"verbrauch_sonstig_kwh": 120.0, "bezug_netz_kwh": 30.0})
    await _inv(db, anlage, "sonstiges", bezeichnung="Noch nicht da",
               anschaffung=date(2025, 12, 1),
               parameter={"kategorie": "erzeuger"},
               vd={"erzeugung_kwh": 999.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    namen = [g.bezeichnung for g in res.sonstiges_geraete]
    assert namen == ["BHKW", "Heizstab"]
    assert res.sonstiges_erzeugung_kwh == 400.0          # ohne die 999
    bhkw = res.sonstiges_geraete[0]
    assert (bhkw.erzeugung_kwh, bhkw.eigenverbrauch_kwh, bhkw.einspeisung_kwh) == (
        400.0, 300.0, 100.0)


# ─────────────────── P4-Semantik: 0 gemessen ≠ keine Daten ───────────────────


async def test_speicher_netzladung_null_bleibt_null_statt_none(db):
    """Ein Speicher mit Zeile, aber ohne Netzladung, meldet 0 — nicht „—".

    Die Unterscheidung hing vorher daran, ob die IMD-Batch für den Typ etwas
    hergab; jetzt an `meta.typen_mit_zeile`. Sie darf dabei nicht verloren
    gehen (Rainer-PN 2026-07-25).
    """
    anlage = await _anlage(db, "speicher-null")
    await _inv(db, anlage, "speicher", parameter={"kapazitaet_kwh": 10.0},
               vd={"ladung_kwh": 100.0, "entladung_kwh": 80.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.speicher_ladung_netz_kwh == 0.0


async def test_speicher_ohne_zeile_meldet_keine_daten(db):
    """Die Gegenprobe: ganz ohne Zeile bleibt es None und die Kachel aus."""
    anlage = await _anlage(db, "speicher-ohne-zeile")
    await _inv(db, anlage, "speicher", parameter={"kapazitaet_kwh": 10.0}, vd=None)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.speicher_ladung_netz_kwh is None
