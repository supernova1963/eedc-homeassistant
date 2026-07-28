"""Der Speicher rechnet netto (`get_speicher_nutzbare_kapazitaet_kwh`, A31-2).

Gegenstück zu `test_speicher_kapazitaet_sot.py` (dort: was **brutto** bleiben
muss). Gesichert wird hier:

1. **Der Helper** — netto mit stillem Brutto-Fallback (Entscheidung **E17**),
   und die Leserichtung geht nur netto → brutto, nie zurück.

2. **Die zwei Pfade aus Entscheidung E-1** — die Tages-Vorschau „Speicher voll
   um …" (`speicher_simulation`, Planungs-Tab **und** HA-Sensor) und die
   Wirtschaftlichkeits-**Prognose** (`berechne_speicher_einsparung` ohne
   IST-Aggregat). Beide inklusive der Nebenwirkungen: die Simulation liefert
   auch Einspeisung, Eigenverbrauch und Autarkie der Vorschau — die ändern
   sich MIT und sind deshalb hier festgehalten, nicht nur die Uhrzeit.

3. **Die Kontrollprobe** — bei ungepflegtem `nutzbare_kapazitaet_kwh` ist
   **jede** Zahl unverändert. Das ist der Kern von E17: die Änderung trifft
   ausschließlich Anlagen, die das Feld bewusst gepflegt haben.

4. **Die Grenze** — die **Vollzyklen** bleiben brutto (Kanon
   `core/berechnungen/speicher.py::vollzyklen`, `f1644cc8`). Der Test dazu ist
   kein Beiwerk: „netto ist doch genauer" ist genau der Gedanke, der den
   Zyklen-Nenner wieder vom Pflegezustand abhängig machen würde.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.core.berechnungen.speicher import vollzyklen
from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.core.calculations import SPEICHER_ZYKLEN_PRO_JAHR, berechne_speicher_einsparung
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.models import Anlage, Investition

HEUTE = date.today()
MORGEN = HEUTE + timedelta(days=1)

_BRUTTO_KWH = 10.0
_NETTO_KWH = 8.0


def _speicher(**kwargs) -> Investition:
    return Investition(typ="speicher", bezeichnung="Speicher", **kwargs)


# ============================================================================
# 1. Der Helper
# ============================================================================

def test_gepflegte_nutzbare_kapazitaet_gewinnt():
    inv = _speicher(parameter={"kapazitaet_kwh": _BRUTTO_KWH,
                               "nutzbare_kapazitaet_kwh": _NETTO_KWH})
    assert get_speicher_nutzbare_kapazitaet_kwh(inv) == _NETTO_KWH


def test_ohne_netto_feld_still_brutto():
    """Entscheidung E17: kein Hinweis, keine Kennzeichnung, kein P4-Fall.

    Der Brutto-Wert ist nicht *unvollständig* — er ist die andere gültige
    Lesart derselben Größe. Deshalb liefert der Helper ihn wortlos.
    """
    inv = _speicher(parameter={"kapazitaet_kwh": _BRUTTO_KWH})
    assert get_speicher_nutzbare_kapazitaet_kwh(inv) == _BRUTTO_KWH


def test_ohne_beides_bleibt_none():
    """E16 gilt weiter: keine erfundene Zahl, auch nicht über den Umweg netto."""
    assert get_speicher_nutzbare_kapazitaet_kwh(_speicher(parameter={})) is None
    assert get_speicher_nutzbare_kapazitaet_kwh(_speicher(parameter=None)) is None


def test_null_im_netto_feld_faellt_auf_brutto():
    """0 ist auch hier „nicht gepflegt", nicht „0 kWh nutzbar" — sonst hätte ein
    versehentlich genulltes Feld den Speicher rechnerisch abgeschaltet."""
    inv = _speicher(parameter={"kapazitaet_kwh": _BRUTTO_KWH, "nutzbare_kapazitaet_kwh": 0})
    assert get_speicher_nutzbare_kapazitaet_kwh(inv) == _BRUTTO_KWH


def test_string_und_muell():
    assert get_speicher_nutzbare_kapazitaet_kwh(
        _speicher(parameter={"nutzbare_kapazitaet_kwh": "8.0"})) == 8.0
    # Unlesbares Netto-Feld → Brutto, nicht None: die Rechnung soll laufen.
    assert get_speicher_nutzbare_kapazitaet_kwh(
        _speicher(parameter={"kapazitaet_kwh": 10, "nutzbare_kapazitaet_kwh": "acht"})
    ) == _BRUTTO_KWH


def test_die_leserichtung_kehrt_nie_um():
    """Das Paar in beide Richtungen geprüft — der eigentliche Anlass von A31.

    netto → brutto ist der erlaubte Fallback (E17). brutto → netto ist die
    verbotene Verwechslung: wer sie einbaut, macht die Vollzyklen davon
    abhängig, ob ein optionales Feld ausgefüllt ist.
    """
    nur_netto = _speicher(parameter={"nutzbare_kapazitaet_kwh": _NETTO_KWH})
    assert get_speicher_nutzbare_kapazitaet_kwh(nur_netto) == _NETTO_KWH
    assert get_speicher_kapazitaet_kwh(nur_netto) is None


# ============================================================================
# 2. Die Grenze: Vollzyklen bleiben brutto
# ============================================================================

def test_vollzyklen_rechnen_weiter_brutto():
    """Kanon `f1644cc8`: Vollzyklen = Entladung ÷ **Brutto**-Kapazität.

    Mit den Zahlen unten: 1000 kWh Entladung ergeben 100,0 Zyklen. Wer den
    Nenner auf netto umstellte, käme auf 125,0 — dieselbe Anlage, dieselbe
    Kachel, eine um ein Viertel höhere Zahl, allein weil jemand ein optionales
    Feld ausgefüllt hat.
    """
    inv = _speicher(parameter={"kapazitaet_kwh": _BRUTTO_KWH,
                               "nutzbare_kapazitaet_kwh": _NETTO_KWH})

    assert vollzyklen(1000.0, get_speicher_kapazitaet_kwh(inv)) == pytest.approx(100.0)
    # Die Gegenzahl explizit benannt, damit ein Umbau hier auffällt:
    assert vollzyklen(1000.0, get_speicher_nutzbare_kapazitaet_kwh(inv)) == pytest.approx(125.0)


# ============================================================================
# 3. Pfad (a): die Tages-Vorschau „Speicher voll um …"
# ============================================================================

def test_simulation_ist_mit_netto_frueher_voll():
    """Handgerechnet, ohne DB: 2 kWh Überschuss je Stunde ab leerem Speicher.

    brutto 10 kWh → 20/40/60/80/100 % ⇒ voll um 04:00.
    netto   8 kWh → 25/50/75/100 %    ⇒ voll um 03:00.

    Genau die Aussage aus E-1: „wer bei 90 % abriegelt, ist real früher voll."
    """
    pv = [2.0] * 24
    verbrauch = [0.0] * 24

    brutto = simuliere_speicher_tag(pv, verbrauch, _BRUTTO_KWH, start_soc_prozent=0.0)
    netto = simuliere_speicher_tag(pv, verbrauch, _NETTO_KWH, start_soc_prozent=0.0)

    assert brutto.speicher_voll_um == "04:00"
    assert netto.speicher_voll_um == "03:00"


def test_der_kleinere_speicher_speist_mehr_ein():
    """Die Nebenwirkung, die mit der Uhrzeit kommt — sie ist der eigentliche
    Zahlensprung in der Vorschau.

    Dieselbe Simulation liefert Einspeisung, Eigenverbrauch und Autarkie der
    Vorschau. Ein kleinerer Speicher nimmt weniger Überschuss auf: mehr geht
    ins Netz, weniger bleibt im Haus. Das ist keine Ungenauigkeit, sondern die
    Korrektur — mit der Brutto-Zahl behauptete die Vorschau eine Aufnahme, die
    der Speicher real nicht leistet.
    """
    pv = [0.0] * 6 + [3.0] * 10 + [0.0] * 8      # 30 kWh
    verbrauch = [0.5] * 24                        # 12 kWh

    brutto = simuliere_speicher_tag(pv, verbrauch, _BRUTTO_KWH, start_soc_prozent=50.0)
    netto = simuliere_speicher_tag(pv, verbrauch, _NETTO_KWH, start_soc_prozent=50.0)

    einsp_brutto = sum(b.einspeisung_kwh for b in brutto.stunden_bilanz)
    einsp_netto = sum(b.einspeisung_kwh for b in netto.stunden_bilanz)
    bezug_brutto = sum(b.netzbezug_kwh for b in brutto.stunden_bilanz)
    bezug_netto = sum(b.netzbezug_kwh for b in netto.stunden_bilanz)

    assert einsp_netto > einsp_brutto, "kleinerer Puffer ⇒ mehr Überschuss ins Netz"
    assert bezug_netto >= bezug_brutto, "und abends weniger Reserve im Speicher"
    # Erhaltungssatz als Gegenprobe: die Simulation verschiebt nur, sie erfindet
    # keine Energie (ΔSoC ist der Rest).
    for sim, kap in ((brutto, _BRUTTO_KWH), (netto, _NETTO_KWH)):
        delta_soc = (sim.end_soc_prozent - 50.0) / 100.0 * kap
        summe = sum(b.pv_kwh - b.verbrauch_kwh for b in sim.stunden_bilanz)
        einsp = sum(b.einspeisung_kwh for b in sim.stunden_bilanz)
        bezug = sum(b.netzbezug_kwh for b in sim.stunden_bilanz)
        assert summe == pytest.approx(einsp - bezug + delta_soc, abs=0.05)


async def _anlage_mit_speicher(db, *, netto: float | None) -> int:
    """Anlage mit Verbrauchshistorie (für die Verbrauchsprognose) + einem
    Speicher, dessen Netto-Feld gepflegt ist oder eben nicht."""
    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage = Anlage(
        anlagenname="A31-2", leistung_kwp=10.0, latitude=48.0, longitude=11.0,
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0, neigung_grad=30.0,
    ))
    parameter: dict = {"kapazitaet_kwh": _BRUTTO_KWH, "wirkungsgrad_prozent": 95}
    if netto is not None:
        parameter["nutzbare_kapazitaet_kwh"] = netto
    db.add(_speicher(
        anlage_id=anlage.id, anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=8000.0, parameter=parameter,
    ))
    for tag_offset in range(1, 15):
        tag = HEUTE - timedelta(days=tag_offset)
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=stunde,
                verbrauch_kw=0.5, pv_kw=0.0,
            ))
    await db.commit()
    return anlage.id


async def _tagesprognose(db, monkeypatch, anlage_id: int):
    """Tagesprognose mit festem PV-Profil — hermetisch, kein Wetterabruf."""
    from backend.api.routes.energie_profil import views

    async def kanon_liefert(*a, **kw):
        return [0.0] * 6 + [3.0] * 10 + [0.0] * 8

    monkeypatch.setattr(views, "_pv_stunden_aus_kanon", kanon_liefert)
    return await views.get_tagesprognose(anlage_id=anlage_id, datum=MORGEN, db=db)


async def test_tagesvorschau_riegelt_bei_der_nutzbaren_kapazitaet_ab(db, monkeypatch):
    """Pfad (a) durch die echte Route — inklusive der drei Bilanzgrößen.

    Die Kapazität kommt aus `energie_profil/views.py`; vor A31-2 stand dort
    die Brutto-Summe. Die Vorschau simulierte dadurch einen Speicher, den es
    so nicht gibt.
    """
    mit_netto = await _tagesprognose(db, monkeypatch, await _anlage_mit_speicher(db, netto=_NETTO_KWH))
    ohne_netto = await _tagesprognose(db, monkeypatch, await _anlage_mit_speicher(db, netto=None))

    # Die Route weist die verwendete Kapazität aus — jetzt die nutzbare.
    assert mit_netto.speicher_kapazitaet_kwh == pytest.approx(_NETTO_KWH)
    assert ohne_netto.speicher_kapazitaet_kwh == pytest.approx(_BRUTTO_KWH)

    # Die Nebenwirkung ist real und geht in die Antwort: weniger Puffer ⇒ mehr
    # Einspeisung, weniger PV-Eigenverbrauch.
    assert mit_netto.einspeisung_summe_kwh > ohne_netto.einspeisung_summe_kwh
    assert mit_netto.eigenverbrauch_kwh < ohne_netto.eigenverbrauch_kwh

    # Die AUTARKIE dagegen bleibt hier beidseitig 100 % — und das ist richtig:
    # dieser Tag kommt in beiden Fällen ohne Netzbezug aus, und wer nichts aus
    # dem Netz zieht, ist vollständig autark, egal wie groß sein Speicher ist.
    #
    # Bis zum N129-Fix (2026-07-28) stand hier `assert mit_netto.autarkie <
    # ohne_netto.autarkie` und war grün — weil die Vorschau die Autarkie damals
    # aus dem PV-Eigenverbrauch rechnete statt aus dem netzunabhängig gedeckten
    # Verbrauch. Die Assertion prüfte also nicht die Autarkie, sondern den
    # Fehler. Sie ist bewusst ersetzt statt gelockert: eine Autarkie, die mit
    # der Speichergröße sinkt, OBWOHL kein Netzbezug entsteht, wäre wieder N129.
    assert mit_netto.netzbezug_summe_kwh == pytest.approx(0.0, abs=0.01)
    assert ohne_netto.netzbezug_summe_kwh == pytest.approx(0.0, abs=0.01)
    assert mit_netto.autarkie_prozent == pytest.approx(100.0)
    assert ohne_netto.autarkie_prozent == pytest.approx(100.0)

    # E17: die Zahlen ändern sich, die Antwort schweigt dazu (kein P4-Hinweis).
    assert mit_netto.hinweise == []


async def test_ha_sensor_speicher_voll_um_nutzt_dieselbe_kapazitaet(db, monkeypatch):
    """E18: der Sensor `eedc_speicher_voll_um` und die KPI-Kachel „Speicher
    voll" tragen denselben Namen und dieselbe Simulation.

    Start-SoC und Start-Stunde unterscheiden sich bewusst (Modul-Docstring von
    `speicher_simulation`) — die Kapazität darf es nicht.
    """
    from backend.services.ha_export_prognose import _aktueller_speicher
    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage_id = await _anlage_mit_speicher(db, netto=_NETTO_KWH)
    db.add(TagesEnergieProfil(
        anlage_id=anlage_id, datum=HEUTE, stunde=8, verbrauch_kw=0.5,
        pv_kw=1.0, soc_prozent=40.0,
    ))
    await db.commit()

    kap, soc = await _aktueller_speicher(db, anlage_id, HEUTE)

    assert kap == pytest.approx(_NETTO_KWH), (
        "Der HA-Sensor lief auf der Brutto-Kapazität weiter — zwei Uhrzeiten "
        "unter demselben Namen."
    )
    assert soc == pytest.approx(40.0)


# ============================================================================
# 4. Pfad (b): die Wirtschaftlichkeits-Prognose
# ============================================================================

def test_prognose_rechnet_netto_durch_den_speicher():
    """Handgerechnet: Kapazität × 250 Zyklen × η × Spread.

    brutto: 10 × 250 × 0,95 = 2375 kWh × 22 ct = 522,50 €
    netto:   8 × 250 × 0,95 = 1900 kWh × 22 ct = 418,00 €

    Die Jahres-Ersparnis ist eine durchgefahrene Energiemenge — durch den
    Speicher geht nur der nutzbare Hub.
    """
    gemeinsam = dict(
        wirkungsgrad_prozent=95, netzbezug_preis_cent=30.0,
        einspeiseverguetung_cent=8.0, nutzt_arbitrage=False,
        zyklen_pro_jahr=SPEICHER_ZYKLEN_PRO_JAHR,
    )
    brutto = berechne_speicher_einsparung(kapazitaet_kwh=_BRUTTO_KWH, **gemeinsam)
    netto = berechne_speicher_einsparung(kapazitaet_kwh=_NETTO_KWH, **gemeinsam)

    assert brutto.jahres_einsparung_euro == pytest.approx(522.50)
    assert netto.jahres_einsparung_euro == pytest.approx(418.00)


async def test_roi_prognose_nimmt_die_nutzbare_kapazitaet(db):
    """Pfad (b) durch die echte Route (`crud.py`, AC-Pfad ohne Hybrid-WR).

    Umfang: **nur** Speicher ohne IST-Aggregat. Wo Lade-/Entladewerte erfasst
    sind, läuft die Rechnung über den Spread-Service und liest die Kapazität
    gar nicht — das sichert `test_ist_modus_bleibt_unberuehrt` unten.
    """
    from backend.api.routes.investitionen.crud import get_roi_dashboard

    async def _ersparnis(netto: float | None) -> float:
        anlage_id = await _anlage_mit_speicher(db, netto=netto)
        res = await get_roi_dashboard(
            anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
            benzinpreis_euro=None, jahr=None, db=db,
        )
        return [b for b in res.berechnungen if b.investition_typ == "speicher"][0].jahres_einsparung

    assert await _ersparnis(_NETTO_KWH) == pytest.approx(418.00)
    assert await _ersparnis(None) == pytest.approx(522.50)


async def test_ist_modus_bleibt_unberuehrt(db):
    """Die Abgrenzung, die den Umfang von Pfad (b) kleiner macht, als er klingt.

    Mit gemessener Entladung delegiert `berechne_speicher_einsparung` an
    `speicher_wirtschaftlichkeit.berechne_speicher_ersparnis` — dort kommt
    keine Kapazität vor. Netto oder brutto ändert dort nichts.
    """
    from backend.api.routes.investitionen.crud import get_roi_dashboard
    from backend.models import InvestitionMonatsdaten

    async def _ersparnis(netto: float | None) -> float:
        anlage_id = await _anlage_mit_speicher(db, netto=netto)
        speicher = (await db.execute(
            __import__("sqlalchemy").select(Investition).where(
                Investition.anlage_id == anlage_id, Investition.typ == "speicher")
        )).scalar_one()
        for monat in range(1, 13):
            db.add(InvestitionMonatsdaten(
                investition_id=speicher.id, jahr=HEUTE.year - 1, monat=monat,
                verbrauch_daten={"ladung_kwh": 110.0, "entladung_kwh": 100.0},
            ))
        await db.commit()
        res = await get_roi_dashboard(
            anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
            benzinpreis_euro=None, jahr=None, db=db,
        )
        roi = [b for b in res.berechnungen if b.investition_typ == "speicher"][0]
        assert roi.detail_berechnung.get("modus") == "ist"
        return roi.jahres_einsparung

    assert await _ersparnis(_NETTO_KWH) == pytest.approx(await _ersparnis(None))


# ============================================================================
# 5. Die Kontrollprobe zu E17
# ============================================================================

async def test_ohne_gepflegtes_netto_feld_aendert_sich_nichts(db, monkeypatch):
    """Der Kern von E17, in einem Test zusammengezogen.

    Eine Anlage ohne `nutzbare_kapazitaet_kwh` — der Normalfall — muss nach
    A31-2 exakt dieselben Zahlen liefern wie davor. „Davor" ist hier die
    Brutto-Kapazität, explizit durchgerechnet statt aus dem Lauf abgeschrieben.
    """
    anlage_id = await _anlage_mit_speicher(db, netto=None)
    resp = await _tagesprognose(db, monkeypatch, anlage_id)

    referenz = simuliere_speicher_tag(
        pv_stunden=[0.0] * 6 + [3.0] * 10 + [0.0] * 8,
        verbrauch_stunden=[0.5] * 24,
        speicher_kap_kwh=_BRUTTO_KWH,
        start_soc_prozent=50.0,
    )

    assert resp.speicher_kapazitaet_kwh == pytest.approx(_BRUTTO_KWH)
    assert resp.speicher_voll_um == referenz.speicher_voll_um
    assert resp.einspeisung_summe_kwh == pytest.approx(
        sum(b.einspeisung_kwh for b in referenz.stunden_bilanz), abs=0.01)
    assert resp.netzbezug_summe_kwh == pytest.approx(
        sum(b.netzbezug_kwh for b in referenz.stunden_bilanz), abs=0.01)
