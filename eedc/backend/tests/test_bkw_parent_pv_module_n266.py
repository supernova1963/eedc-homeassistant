"""Ein Balkonkraftwerk darf PV-Module tragen — und jede Größe zählt einmal (N-266).

**Der Anlass.** Ein `balkonkraftwerk` trägt EINE ``ausrichtung`` und EINE
``neigung_grad`` für das ganze Gerät; zwei Module über Eck waren damit nicht
abbildbar. Der Ausweg über *Einstellungen → PV-Module* war gesperrt, weil ein BKW
kein erlaubter Parent war — obwohl ein `speicher` das seit v4.0.5 darf und ein
BKW funktional „Erzeuger und Wechselrichter in einem" ist. Zwei Melder,
derselbe Punkt: azywietz-web (Discussion #366) und Daniel (Forum T89667 #172).

**Warum das nicht eine Regel-Zeile ist.** Die Menge
``PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")`` wird baumweit gebildet
und **flach summiert**. Bisher zählte dort nichts doppelt, *weil* PV-Module unter
einem `wechselrichter` hängen — und der ist kein PV-Erzeuger-Typ. Unter einem BKW
liegen Eltern **und** Kind in derselben Menge. Betroffen sind drei Größen:

* **kWp** — Nenner des spezifischen Ertrags (verdoppelt ⇒ Kennzahl halbiert) und
  Verteilungsnenner der SOLL-Aufteilung je String,
* **Erzeugung** — ``pv_kwh = pv_modul_summe + bkw_erzeugung``, mit Folgen für
  Autarkie, Eigenverbrauchsquote, CO₂, Finanzen, Community und HA-Export,
* **Ausrichtung** — der Fan-out der Prognose gruppiert danach.

**Was das BKW NICHT abtritt: seine AC-Grenze.** Die 800 VA gehören dem
Wechselrichter-Ausgang, die 2.000 Wp den Modulen — zwei unabhängige Grenzen, und
nur die zweite wächst mit den Kindern. Das BKW wechselt für die Kappung die
Rolle vom Erzeuger zum **Träger**, genau wie ein `wechselrichter` für seine
Strings.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.berechnungen import kwp_aktiv_im_monat, summe_graue_last
from backend.core.berechnungen.erzeuger_traeger import (
    abgetretene_bkw_ids,
    bkw_kwp_aus_kindern,
    erzeuger_traeger,
    modul_kinder,
    traegt_erzeugungsgroessen_selbst,
)
from backend.core.berechnungen.wr_kappung import zuordne_grenzen
from backend.core.investition_kennwerte import get_bkw_kwp, get_erzeuger_kwp
from backend.models.anlage import Anlage
from backend.models.investition import (
    ERLAUBTE_PARENT_TYPEN,
    Investition,
    InvestitionMonatsdaten,
)
from backend.models.monatsdaten import Monatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.pv_orientation import orientierungs_gruppen


# ─── Doubles (kein DB-I/O, wie in test_wr_kappung_dc_speicher_f11.py) ────────

class _Inv:
    """Investition-Double mit genau den Attributen, die die Helper lesen."""

    _naechste_id = [1]

    def __init__(self, typ, **kw):
        self.typ = typ
        self.leistung_kwp = None
        self.parameter = {}
        self.parent_investition_id = None
        self.aktiv = True
        self.anschaffungsdatum = date(2024, 1, 1)
        self.stilllegungsdatum = None
        self.bezeichnung = typ
        self.graue_last_kg = None
        self.id = self._naechste_id[0]
        self._naechste_id[0] += 1
        self.__dict__.update(kw)

    def ist_aktiv_im_monat(self, jahr, monat):
        if not self.aktiv:
            return False
        if self.anschaffungsdatum and (jahr, monat) < (
            self.anschaffungsdatum.year, self.anschaffungsdatum.month
        ):
            return False
        if self.stilllegungsdatum and (jahr, monat) > (
            self.stilllegungsdatum.year, self.stilllegungsdatum.month
        ):
            return False
        return True

    def ist_aktiv_an(self, tag):
        return self.ist_aktiv_im_monat(tag.year, tag.month)


def _bkw(*, grenze_w=800, leistung_wp=500, anzahl=4, **kw):
    """Anker-Solarbank-Muster: 4 × 500 Wp = 2,0 kWp an 800 W AC."""
    return _Inv("balkonkraftwerk", parameter={
        "leistung_wp": leistung_wp, "anzahl": anzahl,
        "wechselrichter_leistung_w": grenze_w,
        "ausrichtung": "sued", "neigung_grad": 30,
    }, **kw)


def _modul(parent_id, kwp=1.0, ausrichtung="Ost", neigung=30, **kw):
    return _Inv(
        "pv-module", leistung_kwp=kwp, parent_investition_id=parent_id,
        ausrichtung=ausrichtung, neigung_grad=neigung, **kw
    )


# ─── 1. Die Regel selbst ────────────────────────────────────────────────────

def test_parent_regel_erlaubt_das_balkonkraftwerk():
    """Der Backend-SoT. Client-Pendant: `test/parent-regel-sot.test.ts`."""
    assert "balkonkraftwerk" in ERLAUBTE_PARENT_TYPEN["pv-module"]
    assert "wechselrichter" in ERLAUBTE_PARENT_TYPEN["pv-module"]


# ─── 2. Der Selektor ────────────────────────────────────────────────────────

def test_bkw_mit_modul_kindern_tritt_ab():
    bkw = _bkw()
    module = [_modul(bkw.id, 1.0, "Ost"), _modul(bkw.id, 1.0, "West")]
    menge = [bkw, *module]

    assert abgetretene_bkw_ids(menge) == frozenset({bkw.id})
    assert erzeuger_traeger(menge) == module
    assert traegt_erzeugungsgroessen_selbst(bkw, menge) is False
    assert all(traegt_erzeugungsgroessen_selbst(m, menge) for m in module)


def test_bkw_ohne_kinder_traegt_weiter_selbst():
    """Bestandsschutz — die Zahl jeder heutigen Anlage bleibt bitgleich."""
    bkw = _bkw()
    assert abgetretene_bkw_ids([bkw]) == frozenset()
    assert erzeuger_traeger([bkw]) == [bkw]
    assert traegt_erzeugungsgroessen_selbst(bkw, [bkw]) is True


def test_modul_am_wechselrichter_tritt_niemandem_etwas_ab():
    """Die Gegenprobe: derselbe Mechanismus darf am WR NICHTS ändern."""
    wr = _Inv("wechselrichter", parameter={"max_leistung_kw": 7.0})
    modul = _modul(wr.id, 8.0)
    assert abgetretene_bkw_ids([wr, modul]) == frozenset()
    assert erzeuger_traeger([wr, modul]) == [wr, modul]


def test_selektor_laesst_fremde_typen_unberuehrt():
    """Er ist ein Drop-in: Reihenfolge und alle übrigen Einträge bleiben."""
    wp = _Inv("waermepumpe")
    bkw = _bkw()
    modul = _modul(bkw.id)
    speicher = _Inv("speicher", parent_investition_id=bkw.id)
    assert erzeuger_traeger([wp, bkw, modul, speicher]) == [wp, modul, speicher]


def test_speicher_kind_allein_loest_keine_abtretung_aus():
    """Der BKW-Akku-Kanon (Speicher mit BKW-Parent) ist KEINE Abtretung —
    sonst hätte diese Etappe jede Anlage mit Anker SOLIX stillgelegt."""
    bkw = _bkw()
    akku = _Inv("speicher", parent_investition_id=bkw.id)
    assert abgetretene_bkw_ids([bkw, akku]) == frozenset()
    assert erzeuger_traeger([bkw, akku]) == [bkw, akku]


def test_teilmenge_irrt_in_die_sichere_richtung():
    """Ohne sichtbare Kinder trägt das BKW seine Größen selbst — also so, wie
    es sich vor dieser Etappe verhalten hat. Die Grenze steht im Docstring."""
    bkw = _bkw()
    _modul(bkw.id)  # existiert, ist der Menge aber nicht übergeben
    assert erzeuger_traeger([bkw]) == [bkw]


def test_modul_kinder_und_kwp_ableitung():
    bkw = _bkw()
    module = [_modul(bkw.id, 1.2), _modul(bkw.id, 0.8)]
    menge = [bkw, *module]
    assert modul_kinder(bkw.id, menge) == module
    assert bkw_kwp_aus_kindern(bkw, menge) == pytest.approx(2.0)
    # Ohne Kinder: `None` = „nicht abgeleitet, die eigene Pflege gilt".
    assert bkw_kwp_aus_kindern(bkw, [bkw]) is None


# ─── 3. kWp-Achse ───────────────────────────────────────────────────────────

def test_kwp_zaehlt_einmal_statt_doppelt():
    """`kwp_aktiv_im_monat` ist der Nenner des spezifischen Ertrags."""
    bkw = _bkw(leistung_wp=500, anzahl=4)              # 2,0 kWp eigene Pflege
    module = [_modul(bkw.id, 1.0), _modul(bkw.id, 1.0)]  # 2,0 kWp aus Kindern
    assert kwp_aktiv_im_monat([bkw, *module], 2025, 6) == pytest.approx(2.0)
    # Bestandsschutz: ohne Kinder unverändert 2,0.
    assert kwp_aktiv_im_monat([bkw], 2025, 6) == pytest.approx(2.0)


def test_monat_vor_der_modul_anschaffung_behaelt_die_bkw_kwp():
    """⚑ Die Reihenfolge Zeitfilter → Selektor ist die eigentliche Aussage.

    Läge der Selektor davor, verlöre dieser Monat den Nenner ganz: das Kind ist
    in der Rohmenge sichtbar (die Abtretung greift), im Monat aber nicht aktiv
    (es zählt nicht mit) — Ergebnis 0 statt 2,0.
    """
    bkw = _bkw(anschaffungsdatum=date(2024, 1, 1))
    spaet = _modul(bkw.id, 1.0, anschaffungsdatum=date(2025, 7, 1))
    assert kwp_aktiv_im_monat([bkw, spaet], 2025, 6) == pytest.approx(2.0)
    assert kwp_aktiv_im_monat([bkw, spaet], 2025, 8) == pytest.approx(1.0)


def test_graue_last_zaehlt_die_module_einmal():
    """Sonst schöbe die Zuordnung die CO₂-Amortisation der Anlage nach hinten."""
    bkw = _bkw()
    module = [_modul(bkw.id, 1.0), _modul(bkw.id, 1.0)]
    mit = summe_graue_last([bkw, *module]).gesamt_kg
    nur_module = summe_graue_last(module).gesamt_kg
    assert mit == pytest.approx(nur_module)


# ─── 4. Ausrichtungs-Achse — der eigentliche Melder-Wunsch ──────────────────

def test_zwei_ausrichtungen_am_balkonkraftwerk():
    """Genau das, was zwei Melder wollten: Ost UND West an einem BKW."""
    bkw = _bkw()
    ost = _modul(bkw.id, 1.0, ausrichtung="Ost", neigung=30)
    west = _modul(bkw.id, 1.0, ausrichtung="West", neigung=30)

    gruppen = orientierungs_gruppen([bkw, ost, west])
    assert len(gruppen) == 2, "das BKW brächte sonst seine Süd-Gruppe als dritte mit"
    assert {g.ausrichtung for g in gruppen} == {-90, 90}
    assert sum(g.kwp for g in gruppen) == pytest.approx(2.0)


def test_bkw_ohne_kinder_bleibt_eine_gruppe():
    bkw = _bkw()
    gruppen = orientierungs_gruppen([bkw])
    assert len(gruppen) == 1
    assert gruppen[0].kwp == pytest.approx(get_erzeuger_kwp(bkw))


# ─── 5. AC-Grenze — das BKW tritt sie NICHT ab (E6) ─────────────────────────

def test_module_teilen_sich_die_ac_grenze_des_balkonkraftwerks():
    """800 VA für die SUMME der Module, nicht je Modul.

    Je Modul angewandt lieferte ein 800-W-Gerät mit zwei Strings 1.600 W — genau
    der Fehler, den #354 am Dach-Wechselrichter behoben hat.
    """
    bkw = _bkw(grenze_w=800)
    ost = _modul(bkw.id, 1.0, ausrichtung="Ost")
    west = _modul(bkw.id, 1.0, ausrichtung="West")

    z = zuordne_grenzen([bkw, ost, west], [], [])
    assert z[ost.id] == (0.8, f"bkw:{bkw.id}")
    assert z[west.id] == (0.8, f"bkw:{bkw.id}")
    assert z[ost.id][1] == z[west.id][1], "geteilte Grenze, ein Pool"
    # Das abtretende BKW selbst ist keine Erzeuger-Zeile mehr.
    assert bkw.id not in z


def test_bkw_ohne_kinder_behaelt_seine_eigene_grenze():
    """Bestandsschutz für die Kappung — `inv:` bleibt `inv:`."""
    bkw = _bkw(grenze_w=800)
    assert zuordne_grenzen([bkw], [], [])[bkw.id] == (0.8, f"inv:{bkw.id}")


def test_dc_speicher_am_balkonkraftwerk_setzt_die_kappung_auch_fuer_die_kinder_aus():
    """F-11 greift über die neue Träger-Ebene hinweg: läuft der Überschuss in
    den BKW-Akku, ist er nicht verloren und darf nicht weggerechnet werden."""
    bkw = _bkw(grenze_w=800)
    modul = _modul(bkw.id, 1.0)
    akku = _Inv("speicher", parent_investition_id=bkw.id)  # Parent ⇒ DC (N-268)
    assert zuordne_grenzen([bkw, modul], [], [akku])[modul.id] == (None, None)


def test_modul_am_wechselrichter_behaelt_das_wr_praefix():
    """Gegenprobe zur neuen `bkw:`-Kennung — der WR-Pfad ist unberührt."""
    wr = _Inv("wechselrichter", parameter={"max_leistung_kw": 7.0})
    modul = _modul(wr.id, 8.0)
    assert zuordne_grenzen([modul], [wr], [])[modul.id] == (7.0, f"wr:{wr.id}")


# ─── 6. kWp-Ableitung am Gerät (E5) — nur ohne Lazy-Zugriff ─────────────────

def test_get_bkw_kwp_ohne_orm_objekt_bleibt_bei_der_eigenen_pflege():
    """Test-Doubles haben keine `children`-Beziehung — dann schweigt die
    Ableitung, statt zu raten."""
    assert get_bkw_kwp(_bkw(leistung_wp=500, anzahl=4)) == pytest.approx(2.0)


async def test_get_bkw_kwp_liest_geladene_kinder(db):
    anlage = Anlage(anlagenname="BKW über Eck", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        # Eigene Pflege bewusst ABWEICHEND von der Σ der Kinder — nur so zeigt
        # der Test, welche der beiden Zahlen gewinnt.
        parameter={"leistung_wp": 500, "anzahl": 4},  # 2,0 kWp
    )
    db.add(bkw)
    await db.flush()
    for kwp, ausr in ((0.6, "Ost"), (0.6, "West")):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"Modul {ausr}",
            anschaffungsdatum=date(2024, 1, 1), aktiv=True,
            leistung_kwp=kwp, ausrichtung=ausr, neigung_grad=30,
            parent_investition_id=bkw.id,
        ))
    await db.commit()

    # Ohne geladene Kinder: die eigene Pflege (kein Lazy-Zugriff, kein Raten).
    ohne = (await db.execute(
        select(Investition).where(Investition.id == bkw.id)
    )).scalar_one()
    assert get_bkw_kwp(ohne) == pytest.approx(2.0)

    # Mit `selectinload`: die Σ der Kinder gewinnt.
    mit = (await db.execute(
        select(Investition)
        .where(Investition.id == bkw.id)
        .options(selectinload(Investition.children))
    )).scalar_one()
    assert get_bkw_kwp(mit) == pytest.approx(1.2)


async def test_kinder_ohne_gepflegte_kwp_lassen_die_eigene_pflege_stehen(db):
    """Σ = 0 heißt „die Kinder sagen nichts" — sonst hätte die Zuordnung die
    Nennleistung auf 0 gesetzt und mit ihr die ganze Prognose."""
    anlage = Anlage(anlagenname="BKW ohne Modul-kWp", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"leistung_wp": 500, "anzahl": 4},
    )
    db.add(bkw)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Modul ohne kWp",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parent_investition_id=bkw.id,
    ))
    await db.commit()

    mit = (await db.execute(
        select(Investition)
        .where(Investition.id == bkw.id)
        .options(selectinload(Investition.children))
    )).scalar_one()
    assert get_bkw_kwp(mit) == pytest.approx(2.0)


# ─── 7. Energie-Achse (E4) — die gefährlichere der beiden ───────────────────

async def _anlage_bkw_mit_modulen(db, *, bkw_kwh=None, modul_kwh=None):
    """BKW mit zwei Modul-Kindern über Eck, ein Monat (06/2025).

    ``bkw_kwh`` = Monatswert am BKW, ``modul_kwh`` = ``{index: kwh}`` je Modul.
    """
    anlage = Anlage(
        anlagenname="BKW über Eck", leistung_kwp=1.2,
        installationsdatum=date(2024, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"leistung_wp": 600, "anzahl": 2,
                   "ausrichtung": "sued", "neigung_grad": 30},
    )
    db.add(bkw)
    await db.flush()
    module = []
    for ausr in ("Ost", "West"):
        m = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"Modul {ausr}",
            anschaffungsdatum=date(2024, 1, 1), aktiv=True,
            leistung_kwp=0.6, ausrichtung=ausr, neigung_grad=30,
            parent_investition_id=bkw.id,
        )
        db.add(m)
        module.append(m)
    await db.flush()

    # Zählerzeile — ohne sie gibt es keine Hausbilanz.
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=40.0, netzbezug_kwh=100.0,
    ))
    if bkw_kwh is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=2025, monat=6,
            verbrauch_daten={"pv_erzeugung_kwh": bkw_kwh},
        ))
    for idx, kwh in (modul_kwh or {}).items():
        db.add(InvestitionMonatsdaten(
            investition_id=module[idx].id, jahr=2025, monat=6,
            verbrauch_daten={"pv_erzeugung_kwh": kwh},
        ))
    await db.commit()
    return anlage, bkw, module


async def test_erzeugung_zaehlt_einmal_nicht_zweimal(db):
    """⚑ Der Kern von E4. Beide Seiten gepflegt: 100 am BKW, 60+40 an den
    Modulen. `pv_kwh` muss 100 sein, nicht 200."""
    anlage, bkw, _ = await _anlage_bkw_mit_modulen(
        db, bkw_kwh=100.0, modul_kwh={0: 60.0, 1: 40.0}
    )
    fakt = (await lade_monats_fakten(db, anlage.id))[0]
    assert fakt.erzeugung.pv_kwh == pytest.approx(100.0)
    assert fakt.erzeugung.pv_module_kwh == pytest.approx(100.0)
    assert fakt.bkw.erzeugung_kwh == pytest.approx(0.0), (
        "das abgetretene BKW ist kein eigener Summand mehr"
    )
    assert fakt.bkw.erzeugung_je_investition == {}, (
        "sonst zählt die ROI-Gewichtung in `aussichten.py` es ein zweites Mal"
    )


async def test_bkw_wert_fuellt_die_luecken_seiner_kinder(db):
    """Stufe 2 der P7-Präzedenz: ein gemessenes Modul gewinnt, der BKW-Wert
    verteilt nur den Rest — hier hat kein Modul einen eigenen Wert."""
    anlage, _bkw, module = await _anlage_bkw_mit_modulen(db, bkw_kwh=100.0)
    fakt = (await lade_monats_fakten(db, anlage.id))[0]
    assert fakt.erzeugung.pv_kwh == pytest.approx(100.0)
    je_modul = fakt.erzeugung.pv_je_modul
    # Gleiche kWp ⇒ 50/50, und beide als *verteilt* markiert (nicht gemessen).
    assert je_modul[module[0].id].pv_erzeugung_kwh == pytest.approx(50.0)
    assert je_modul[module[1].id].pv_erzeugung_kwh == pytest.approx(50.0)
    assert je_modul[module[0].id].quelle != "gemessen"


async def test_gemessener_modulwert_gewinnt_gegen_den_bkw_wert(db):
    """Das nähere Aggregat füllt nur Lücken — es überschreibt keine Messung."""
    anlage, _bkw, module = await _anlage_bkw_mit_modulen(
        db, bkw_kwh=100.0, modul_kwh={0: 70.0}
    )
    fakt = (await lade_monats_fakten(db, anlage.id))[0]
    je_modul = fakt.erzeugung.pv_je_modul
    assert je_modul[module[0].id].pv_erzeugung_kwh == pytest.approx(70.0)
    assert je_modul[module[0].id].quelle == "gemessen"
    # Rest 100 − 70 = 30 auf das lückenhafte Modul.
    assert je_modul[module[1].id].pv_erzeugung_kwh == pytest.approx(30.0)
    assert fakt.erzeugung.pv_kwh == pytest.approx(100.0)


async def test_bkw_ohne_kinder_bleibt_ein_eigener_summand(db):
    """Bestandsschutz auf der Energie-Achse: eine reine BKW-Anlage rechnet
    unverändert über `bkw_erzeugung`."""
    anlage = Anlage(
        anlagenname="Nur BKW", leistung_kwp=0.8,
        installationsdatum=date(2024, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"leistung_wp": 400, "anzahl": 2},
    )
    db.add(bkw)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=40.0, netzbezug_kwh=100.0,
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=bkw.id, jahr=2025, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 90.0},
    ))
    await db.commit()

    fakt = (await lade_monats_fakten(db, anlage.id))[0]
    assert fakt.bkw.erzeugung_kwh == pytest.approx(90.0)
    assert fakt.erzeugung.pv_kwh == pytest.approx(90.0)
    assert fakt.bkw.erzeugung_je_investition == {bkw.id: pytest.approx(90.0)}


async def test_autarkie_bleibt_unter_hundert_prozent(db):
    """Die sichtbare Folge der Doppelzählung in einer Zahl: mit 200 statt 100
    kWh PV stünde die Anlage über der Wirklichkeit."""
    anlage, _bkw, _ = await _anlage_bkw_mit_modulen(
        db, bkw_kwh=100.0, modul_kwh={0: 60.0, 1: 40.0}
    )
    fakt = (await lade_monats_fakten(db, anlage.id))[0]
    # Haus = PV − Einspeisung + Netzbezug = 100 − 40 + 100 = 160
    assert fakt.erzeugung.hinter_zaehler_kwh == pytest.approx(100.0)
    assert fakt.kennzahlen.gesamtverbrauch_kwh == pytest.approx(160.0)
    assert fakt.kennzahlen.autarkie_prozent == pytest.approx(37.5)
