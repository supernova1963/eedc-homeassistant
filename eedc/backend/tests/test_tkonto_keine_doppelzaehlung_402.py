"""Σ-Symmetrie des T-Kontos: keine Kilowattstunde zählt zweimal (#402).

**Der Melder.** rilmor-mhrs berichtet drei Dinge an *Auswertungen → Finanzen*
(2026-09-02): der gepflegte Einspeise-Erlös seiner *Sonstigen* Erzeuger fehlt,
*Cockpit → Monat → Finanzen* und das T-Konto nennen für „PV-Anlage" verschiedene
Zahlen, und die Betriebskosten eines E-Autos laufen elf Monate vor dem Kauf.

**Was diese Datei prüft** ist die gemeinsame Wurzel der ersten beiden: eine
Größe, die an zwei Stellen bewertet wird. Die Anlage hier ist bewusst die
schwierigste Konstellation — PV **und** Speicher **und** Balkonkraftwerk **und**
ein Erzeuger unter *Sonstiges* —, weil genau deren Überlagerung den Fehler
erzeugt. Bei einer reinen PV-Anlage stimmen beide Sichten auch vorher überein;
eine Probe ohne Speicher hätte nichts gemessen.

**Die Invariante in einem Satz:** Σ HABEN des T-Kontos zählt jede bewertete
Kilowattstunde genau einmal — der anlagenweite Posten trägt nur, was keine
Gerätezeile schon trägt.

Schwester-Testdateien (Symbol `get_aktueller_monat` / T-Konto-Fläche):
  - test_aktueller_monat_tkonto.py            (Zeile je Investitionstyp)
  - test_aktueller_monat_financial_builder.py (der Builder isoliert)
  - test_speicher_kanon_symmetrie.py          (Speicher-Zeile gegen den Layer)
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2024, 5
NETZ_CT, EINSP_CT = 30.0, 8.0


async def _anlage_mit_allem(db: AsyncSession, *, bhkw_erloes_gepflegt=None) -> Anlage:
    """PV 1000 kWh · Speicher · BKW · Mini-BHKW hinter DEMSELBEN Hauszähler.

    Der Hauszähler misst 750 kWh Einspeisung — darin stecken die 150 kWh des
    BHKW, denn an einem Netzanschluss misst er die Summe aller dahinter
    liegenden Erzeuger (`erzeugung_hinter_zaehler_kwh`). Genau daraus entsteht
    die Doppelzählung, wenn dieselben kWh zusätzlich je Gerät bewertet werden.
    """
    anlage = Anlage(anlagenname="Doppelzaehlung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=NETZ_CT,
        einspeiseverguetung_cent_kwh=EINSP_CT,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       pv_erzeugung_kwh=1000.0, einspeisung_kwh=750.0,
                       netzbezug_kwh=100.0))

    async def add(typ, vd, **kw):
        inv = Investition(anlage_id=anlage.id, typ=typ,
                          bezeichnung=kw.pop("name", typ),
                          anschaffungsdatum=date(2024, 1, 1), **kw)
        db.add(inv)
        await db.flush()
        if vd is not None:
            db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR,
                                          monat=MONAT, verbrauch_daten=vd))
        return inv.id

    await add("pv-module", {"pv_erzeugung_kwh": 1000.0}, name="Dach", leistung_kwp=10.0)
    await add("speicher", {"ladung_kwh": 100.0, "entladung_kwh": 80.0}, name="Akku")
    await add("balkonkraftwerk", {"eigenverbrauch_kwh": 60.0}, name="BKW")
    bhkw_vd = {"erzeugung_kwh": 200.0, "eigenverbrauch_kwh": 50.0,
               "einspeisung_kwh": 150.0}
    if bhkw_erloes_gepflegt is not None:
        bhkw_vd["einspeise_erloes_euro"] = bhkw_erloes_gepflegt
    await add("sonstiges", bhkw_vd, name="Mini-BHKW",
              parameter={"kategorie": "erzeuger"})
    await db.commit()
    return anlage


def _ev_in_komponentenzeilen(fins) -> float:
    """Spiegel von `evAufteilung.ts::evInKomponentenzeilen` (Client-SoT)."""
    return sum(
        (f.ersparnis_euro or 0) for f in fins
        if f.typ in ("balkonkraftwerk", "speicher")
        or (f.typ == "wallbox" and f.ersparnis_label == "PV-Ladung-Ersparnis")
    )


async def test_sigma_haben_zaehlt_jede_kwh_genau_einmal(db):
    """Σ HABEN == anlagenweiter Erlös + anlagenweite EV-Ersparnis + Gerätezeilen,
    die NICHT schon anlagenweit stecken.

    ⛔ Vor dem Fix stand hier 27,00 € zu viel: 15,00 € für den Eigenverbrauch des
    BHKW (50 kWh, die bereits in `ev_ersparnis_euro` bewertet waren) und 12,00 €
    für seine Einspeisung (150 kWh, bereits in `einspeise_erloes_euro`).
    """
    anlage = await _anlage_mit_allem(db)
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    fins = r.investitionen_financials

    # Der Bilanz-Eigenverbrauch trägt den sonstigen Erzeuger mit — das ist
    # richtig und der Grund, warum es daneben keine zweite Bewertung geben darf.
    assert r.eigenverbrauch_kwh == 430.0        # (1000 + 200) − 750 − 100 + 80
    assert r.ev_ersparnis_euro == 129.0         # 430 × 30 ct
    assert r.einspeise_erloes_euro == 60.0      # 750 × 8 ct (inkl. BHKW-Anteil)

    pv_rest = max(0.0, (r.ev_ersparnis_euro or 0) - _ev_in_komponentenzeilen(fins))
    sigma_haben = (
        (r.einspeise_erloes_euro or 0)
        + pv_rest
        + sum((f.ersparnis_euro or 0) + (f.erloes_euro or 0) for f in fins)
    )
    # Ohne jede Doppelzählung ist Σ HABEN exakt die anlagenweite Summe: die
    # Gerätezeilen verteilen sie, sie vergrößern sie nicht.
    assert round(sigma_haben, 2) == round(
        (r.einspeise_erloes_euro or 0) + (r.ev_ersparnis_euro or 0), 2
    ) == 189.0


async def test_sonstiger_erzeuger_bekommt_keine_eigene_bewertung(db):
    """N-131 (Entscheid 2026-09-01): den Nutzen eines sonstigen Erzeugers
    rechnet eedc nicht selbst — er wird am Gerät als „Ertrag/Jahr" gepflegt."""
    anlage = await _anlage_mit_allem(db)
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    bhkw = [f for f in r.investitionen_financials if f.bezeichnung == "Mini-BHKW"]
    assert bhkw == [], "Erzeuger unter Sonstiges wird je Gerät nicht bewertet"


async def test_gepflegter_erloes_kommt_an_und_wird_nicht_nachgerechnet(db):
    """Konzept §9 Weg 2 — der einzige Weg, auf dem ein sonstiger Erzeuger Geld
    in diese Sicht bringt: ein gepflegter Betrag mit eigenem Vergütungssatz."""
    anlage = await _anlage_mit_allem(db, bhkw_erloes_gepflegt=42.0)
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    bhkw = [f for f in r.investitionen_financials if f.bezeichnung == "Mini-BHKW"]
    assert len(bhkw) == 1
    # 42,00 €, NICHT 12,00 € (= 150 kWh × 8 ct) — der Betrag ist gepflegt, nicht
    # gerechnet; er gehört zu einem eigenen Zähler mit eigenem Satz.
    assert bhkw[0].erloes_euro == 42.0
    assert bhkw[0].ersparnis_euro is None


async def test_betriebskosten_erst_ab_der_anschaffung(db):
    """Der dritte Punkt aus #402: ein Gerät, das es im Berichtsmonat noch gar
    nicht gab, trug seine anteiligen Jahres-Betriebskosten trotzdem."""
    anlage = await _anlage_mit_allem(db)
    spaeter = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Spaetkauf",
        anschaffungsdatum=date(2025, 8, 14), betriebskosten_jahr=50.04,
    )
    db.add(spaeter)
    await db.commit()

    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert [f for f in r.investitionen_financials if f.bezeichnung == "Spaetkauf"] == []

    # Gegenprobe in der anderen Richtung: im Monat der Anschaffung ist es da.
    r2 = await get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=8, db=db)
    zeile = [f for f in r2.investitionen_financials if f.bezeichnung == "Spaetkauf"]
    assert len(zeile) == 1
    assert zeile[0].betriebskosten_monat_euro == 4.17


async def test_stilllegung_beendet_die_betriebskosten(db):
    """Dieselbe Grenze am anderen Ende — ein stillgelegtes Gerät kostet nichts
    mehr. `ist_aktiv_im_zeitraum` prüft beide Daten; die Probe hält beide fest,
    damit ein späterer Fix nicht nur die halbe Grenze wiederherstellt."""
    anlage = await _anlage_mit_allem(db)
    alt = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Verkauft",
        anschaffungsdatum=date(2020, 1, 1), stilllegungsdatum=date(2023, 6, 30),
        betriebskosten_jahr=50.04,
    )
    db.add(alt)
    await db.commit()

    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert [f for f in r.investitionen_financials if f.bezeichnung == "Verkauft"] == []


async def test_beide_routen_nennen_dieselbe_ev_ersparnis(db):
    """N-375: *Cockpit/T-Konto* und *Auswertungen -> Finanzen* rechnen die
    Eigenverbrauchs-Ersparnis aus derselben Erzeugung.

    **Der Vertrag** (Maintainer, 2026-09-03): Ein Erzeuger unter *Sonstiges* wird
    als **Komponente** nicht wirtschaftlich ausgewertet — sein Strom geht aber
    **vollständig** in EV-Ersparnis und Einspeisung der **Anlage** auf.

    ⛔ Bis 2026-09-03 nannten die beiden Sichten verschiedene Betraege, und der
    Wert der zweiten entsprach keiner Lesart: `finanz_zeile_eingabe` uebergab die
    **PV allein** als Erzeugung, aber die **Hauszaehler**-Einspeisung als Abzug.
    Bei dieser Anlage: 250 kWh / 75,00 EUR gegen 450,0 kWh / 135,00 EUR — und die
    Mengenspalte derselben Antwort wies 450,0 aus.

    ⚠ Die Probe braucht den sonstigen Erzeuger. Ohne ihn sind `pv_kwh` und
    `hinter_zaehler_kwh` identisch und beide Fassungen waeren gruen.
    """
    anlage = await _anlage_mit_allem(db)
    a = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    zeilen = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=JAHR, db=db)
    b = [z for z in zeilen if z.monat == MONAT][0]

    # Die Menge war nie strittig — sie traegt den sonstigen Erzeuger in beiden.
    assert a.eigenverbrauch_kwh == b.eigenverbrauch_kwh == 430.0
    # Und der Geldwert folgt ihr jetzt in beiden, mit demselben Preis.
    assert a.ev_ersparnis_euro == b.ev_ersparnis_euro == 129.0
    # Menge x Preis geht auf — das ist die eigentliche Aussage.
    assert round(b.eigenverbrauch_kwh * 0.30, 2) == b.ev_ersparnis_euro
    # Die Einspeise-Seite war schon vorher deckungsgleich (Hauszaehler).
    assert a.einspeise_erloes_euro == b.einspeise_erloes_euro == 60.0
