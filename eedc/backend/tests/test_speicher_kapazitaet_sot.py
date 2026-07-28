"""SoT-Helper für die Speicher-Kapazität (`get_speicher_kapazitaet_kwh`, A31-1).

Drei Dinge werden hier gesichert:

1. **Der Helper selbst** — inkl. Entscheidung E16 (`None` statt `0.0` bei
   ungepflegter Kapazität) und der beiden bewusst NICHT gebauten Fallbacks
   (keine Spalte, kein Netto-Wert).

2. **Die Negativ-Verifikation** — eine Anlage mit einem Speicher **ohne**
   gepflegte Kapazität durch alle migrierten Lesestellen geschickt. Der Anspruch
   ist nicht „es kracht nicht", sondern: **nirgends entsteht eine Zahl.**
   Vor A31-1 hätte derselbe Speicher an drei Stellen 10 kWh behauptet und daraus
   Vollzyklen und eine Jahres-Ersparnis gerechnet.

3. **N127 im Detail** — der 10-kWh-Default ist an allen drei Fundstellen weg
   (`investitionen/crud.py` DC- und AC-Pfad, `investitionen/dashboards.py`),
   und was stattdessen passiert, steht in der Antwort statt im Log (P4).

Seit **A31-3 ein baumweiter Wächter** (Abschnitt 3), nicht mehr eine Regression
über eine Dateiliste. Die Vorbedingung dafür kam mit A31-2: die drei
Brutto-mit-Netto-Fallback-Konstrukte sind aufgelöst, alle migrierten Stellen
lesen über die Helper, die Baseline im Backend-Baum ist 0.

**Die namentliche Dateiliste ist mit A31-3 entfallen**, nicht vergessen: der
baumweite Test deckte jede ihrer 13 Einträge vollständig ab. Eine Liste, die
nichts mehr sichert, aber bei jeder neuen Datei nachgepflegt werden müsste, ist
Wartungslast ohne Gegenwert — und sie hätte den Wächter daneben schwächer
aussehen lassen, als er ist. Was migriert wurde, steht im Commit und im
Register, nicht in einer Testkonstante.

Die **Netto**-Seite (`get_speicher_nutzbare_kapazitaet_kwh`, A31-2) hat ihre
eigene Datei: `test_speicher_netto_kapazitaet.py`. Hier steht nur, was brutto
bleiben muss.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.core.berechnungen.co2_amortisation import graue_last_einzeln
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.community_service import prepare_community_data
from backend.services.daten_checker import DatenChecker


def _speicher(**kwargs) -> Investition:
    return Investition(typ="speicher", bezeichnung="Speicher", **kwargs)


# ============================================================================
# 1. Der Helper
# ============================================================================

def test_gepflegte_kapazitaet_kommt_als_float():
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": 12.5})) == 12.5


def test_string_wert_wird_konvertiert():
    """Formulare liefern Zahlen gelegentlich als String — das ist kein `None`-Fall."""
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": "12.5"})) == 12.5


def test_ungepflegt_ist_none_nicht_null():
    """Entscheidung E16: der Aufrufer entscheidet, aber erfindet keine Zahl.

    `0.0` wäre die bequeme Rückgabe — und genau die Falle: sie ist von einem
    echten Messwert nicht zu unterscheiden und rutscht still in jede Σ.
    """
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={})) is None
    assert get_speicher_kapazitaet_kwh(_speicher(parameter=None)) is None
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"wirkungsgrad_prozent": 95})) is None


def test_null_zaehlt_als_ungepflegt():
    """0 kWh ist kein Speicher, sondern ein leeres Feld — dieselbe Semantik wie
    beim `get_pv_kwp`-0-Fall. Der Daten-Checker sieht das genauso (`if not kap`)."""
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": 0})) is None
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": None})) is None


def test_muell_wird_nicht_zur_zahl():
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": "zehn"})) is None
    assert get_speicher_kapazitaet_kwh(_speicher(parameter={"kapazitaet_kwh": []})) is None


def test_kein_fallback_auf_die_nutzbare_kapazitaet():
    """Brutto und netto sind zwei Zahlen, nicht zwei Genauigkeitsstufen.

    Der Helper liefert BRUTTO. Ein stiller Netto-Fallback wäre genau die
    Verwechslung, gegen die dieses Paket gebaut ist — die Vollzyklen einer
    Anlage sprängen dann je nachdem, ob jemand das optionale Netto-Feld
    ausgefüllt hat. (Die drei existierenden Fallback-Konstrukte im Baum sind
    A31-2, s. Modul-Docstring.)
    """
    inv = _speicher(parameter={"nutzbare_kapazitaet_kwh": 8.0})
    assert get_speicher_kapazitaet_kwh(inv) is None


def test_kein_fallback_auf_die_mehrzweck_spalte():
    """`Investition.leistung_kwp` trägt beim Speicher zwar kWh, aber kein
    Schreibpfad füllt sie dort (gemessen A31-1: das Formular bietet das Feld nur
    für `pv-module` an). Sie zu lesen wäre keine Härtung, sondern eine
    Verhaltensänderung an jeder Lesestelle."""
    inv = _speicher(leistung_kwp=9.9, parameter={})
    assert get_speicher_kapazitaet_kwh(inv) is None


def test_fremder_typ_liefert_keine_kapazitaet():
    """Ein E-Auto trägt seine Batterie unter `batteriekapazitaet_kwh`."""
    eauto = Investition(typ="e-auto", bezeichnung="Auto", parameter={"batteriekapazitaet_kwh": 75})
    assert get_speicher_kapazitaet_kwh(eauto) is None


# ============================================================================
# 2. Negativ-Verifikation: ein Speicher ohne Kapazität durch alle Lesestellen
# ============================================================================

_LADUNG_KWH = 1100.0
_ENTLADUNG_KWH = 1000.0

# Was ein 10-kWh-Default aus diesen Daten gemacht hätte. Steht hier, damit die
# Assertions nicht nur „nicht 10" prüfen, sondern die konkrete Falschzahl
# benennen können.
_ZYKLEN_BEI_10_KWH = _ENTLADUNG_KWH / 10.0  # 100,0 Vollzyklen aus dem Nichts


async def _lade(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _seed_ohne_kapazitaet(db) -> Anlage:
    """Der erreichbare Fall: `kapazitaet_kwh` ist im Formular optional
    (`lib/investitionParameter.ts`), Lade-/Entladewerte sind trotzdem da —
    sie kommen aus Sensoren, nicht aus der Stammdatenpflege."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    inv = _speicher(
        anlage_id=anlage.id,
        anschaffungsdatum=date(2023, 7, 1),
        anschaffungskosten_gesamt=8000.0,
        # Alles gepflegt AUSSER der Kapazität.
        parameter={"wirkungsgrad_prozent": 95},
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": _LADUNG_KWH, "entladung_kwh": _ENTLADUNG_KWH},
    ))
    await db.commit()
    return await _lade(db, anlage.id)


async def test_speicher_dashboard_erfindet_keine_kapazitaet(db):
    """N127-Fundstelle 3 (`dashboards.py`) — die vom Auftragstext nicht genannte."""
    anlage = await _seed_ohne_kapazitaet(db)

    zus = (await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    ))[0].zusammenfassung

    assert zus["kapazitaet_kwh"] is None
    assert zus["vollzyklen"] is None, (
        f"{zus['vollzyklen']} — mit dem alten 10-kWh-Default stünden hier "
        f"{_ZYKLEN_BEI_10_KWH} Vollzyklen"
    )
    assert zus["zyklen_pro_monat"] is None
    # P4: die Antwort sagt selbst, warum die Zahlen fehlen.
    assert zus["kapazitaet_fehlt"] is True


async def test_roi_erfindet_keine_jahres_ersparnis(db):
    """N127-Fundstellen 1+2 (`crud.py` AC-Pfad, hier ohne Hybrid-WR).

    Der eigentliche Schaden: aus 10 erfundenen kWh entstand über
    `berechne_speicher_einsparung` eine vierstellige Jahres-Ersparnis und
    daraus eine Amortisationszeit — für einen Speicher, über dessen Größe
    das System nichts weiß.
    """
    anlage = await _seed_ohne_kapazitaet(db)

    res = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0, benzinpreis_euro=None, jahr=None, db=db,
    )

    speicher_roi = [b for b in res.berechnungen if b.investition_typ == "speicher"]
    assert len(speicher_roi) == 1, "Die Komponente verschwindet nicht — die Kosten sind real"
    roi = speicher_roi[0]
    assert roi.jahres_einsparung == 0.0
    assert res.gesamt_jahres_einsparung == 0.0
    # ... und sie sagt, dass das ein fehlender Wert ist und keine Null-Ersparnis.
    assert roi.detail_berechnung.get("kapazitaet_fehlt") is True
    assert "Kapazität" in roi.detail_berechnung.get("hinweis", "")
    # Keine Amortisation aus dem Nichts.
    assert roi.amortisation_jahre is None


async def test_ist_modus_rechnet_weiter_ohne_kapazitaet(db):
    """Gegenprobe zur Regression: die Kapazität geht NUR in den Prognose-Modus ein.

    Liegen gemessene IMD-Werte vor, rechnet `berechne_speicher_einsparung` aus
    der Entladung und liest die Kapazität gar nicht. Hier eine echte Ersparnis
    zu unterdrücken wäre kein Fix, sondern ein neuer Defekt.
    """
    anlage = await _seed_ohne_kapazitaet(db)
    # Ein volles Jahr IMD ⇒ der ROI schaltet auf den IST-Pfad.
    speicher = next(i for i in anlage.investitionen if i.typ == "speicher")
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=monat,
            verbrauch_daten={"ladung_kwh": 110.0, "entladung_kwh": 100.0},
        ))
    await db.commit()

    res = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0, benzinpreis_euro=None, jahr=None, db=db,
    )

    roi = [b for b in res.berechnungen if b.investition_typ == "speicher"][0]
    assert roi.jahres_einsparung > 0, "IST-Modus braucht keine Kapazität"
    assert roi.detail_berechnung.get("modus") == "ist"
    assert roi.detail_berechnung.get("kapazitaet_fehlt") is None


async def test_monatsbericht_meldet_keine_kapazitaet(db):
    anlage = await _seed_ohne_kapazitaet(db)

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)

    assert res.speicher_kapazitaet_kwh is None
    assert res.speicher_vollzyklen is None, (
        f"{res.speicher_vollzyklen} — ein 10-kWh-Default ergäbe {_ZYKLEN_BEI_10_KWH}"
    )


async def test_cockpit_meldet_keine_kapazitaet(db):
    anlage = await _seed_ohne_kapazitaet(db)

    res = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    assert res.speicher_kapazitaet_kwh == 0
    assert res.speicher_vollzyklen is None


async def test_daten_checker_weist_den_fehlenden_wert_aus(db):
    """Die Bedingung, unter der E16 freigegeben wurde.

    Gernots Bedingung für `None` war, dass der fehlende Wert sichtbar ist. Trägt
    diese Meldung nicht, ist die ganze Entscheidung nicht gedeckt — deshalb
    steht sie hier als Test und nicht nur als Kommentar.
    """
    anlage = await _seed_ohne_kapazitaet(db)

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    treffer = [e for e in ergebnisse if "Kapazität" in e.meldung]
    assert len(treffer) == 1, f"Meldung fehlt — E16 wäre ungedeckt. Gefunden: {[e.meldung for e in ergebnisse]}"
    assert treffer[0].link == "/einstellungen/investitionen"


async def test_community_datensatz_meldet_null_statt_zehn(db):
    anlage = await _seed_ohne_kapazitaet(db)

    daten = await prepare_community_data(db, anlage.id)

    assert daten is not None
    assert daten.get("speicher_kwh") in (0, None), (
        f"{daten.get('speicher_kwh')} — ein erfundener Kapazitätswert würde "
        "den Community-Benchmark verzerren"
    )


def test_graue_last_bleibt_unermittelt():
    """CO₂-Amortisation: ohne Kapazität keine graue Last — und das sagt die
    Quelle auch (`QUELLE_FEHLT`), statt 0 kg als Messwert auszugeben."""
    from backend.core.berechnungen.co2_amortisation import QUELLE_FEHLT

    wert, quelle = graue_last_einzeln(_speicher(parameter={"wirkungsgrad_prozent": 95}))

    assert wert == 0.0
    assert quelle == QUELLE_FEHLT


# ============================================================================
# 3. Wächter: die Kapazität wird baumweit nur über den SoT-Helper gelesen
#    (ADR-002 P3-a, zweites Kennwert-Feld neben `leistung_kwp` — A31-3)
# ============================================================================

_BACKEND = Path(__file__).resolve().parent.parent

_ROH_ZUGRIFF = re.compile(
    r'(get\(\s*"kapazitaet_kwh"|\[\s*"kapazitaet_kwh"\s*\]'
    r'|PARAM_SPEICHER\[\s*"KAPAZITAET_KWH"\s*\])'
)

# Zwei Dateien dürfen den Schlüssel tragen — beide sind die Regel selbst, nicht
# ihre Umgehung. Klartext statt stiller Auslassung (ADR-002 Pflicht Nr. 2):
_WAECHTER_AUSNAHMEN = {
    # Der Kanon führt die Schlüssel-Konstanten; ohne ihn gäbe es nichts zu prüfen.
    "core/investition_parameter.py",
    # Der SoT-Helper MUSS roh lesen — er ist die eine Stelle, die es darf.
    "core/investition_kennwerte.py",
}


def test_p3a_kapazitaet_nur_ueber_den_sot_helper():
    """Baumweit: niemand außer dem SoT-Helper liest die Kapazität roh.

    **Warum baumweit und nicht über eine Dateiliste** (so stand es bis A31-2):
    eine namentliche Liste sichert nur die Stellen, die es beim Schreiben des
    Tests schon gab. Genau daran ist die #229-Klasse jahrelang vorbeigelaufen —
    `co2_amortisation.py` las per `getattr` und tauchte in keiner Erhebung auf
    (ADR-002, P3-a-Zeile). Ein Wächter fängt auch die Stelle, die es heute noch
    nicht gibt; eine Regression tut das nicht, und der Unterschied gehört
    benannt statt behauptet.

    **Warum die Schreibseite hier kein Thema ist:** der Regex erfasst auch
    `parameter["kapazitaet_kwh"] = …`, und die Baseline ist trotzdem 0 — im
    Backend schreibt niemand den Schlüssel als Literal (Formular und Import
    laufen über die Pydantic-Modelle). Fällt dieser Test künftig mit einem
    Schreibpfad an, ist das eine echte neue Stelle, keine Falschmeldung.
    """
    treffer = {
        str(p.relative_to(_BACKEND)): len(_ROH_ZUGRIFF.findall(p.read_text(encoding="utf-8")))
        for p in _BACKEND.rglob("*.py")
        if "tests" not in p.parts
    }
    offen = {
        p: n for p, n in treffer.items()
        if n and p not in _WAECHTER_AUSNAHMEN
    }
    assert offen == {}, f"Roh-Zugriff auf die Kapazität außerhalb des SoT-Helpers: {offen}"


def test_p3a_kapazitaet_ausnahmen_sind_noch_belegt():
    """Verhindert eine verwaiste Ausnahme, die später einen echten Treffer deckt.

    Dieselbe Mechanik wie `test_p3a_baseline_ausnahmen_sind_noch_belegt` in
    `test_wurzelmuster_konformitaet.py`: wer eine Ausnahme stehen lässt, deren
    Grund weggefallen ist, hat ein Loch im Wächter statt einer Ausnahme.
    """
    for pfad in _WAECHTER_AUSNAHMEN:
        datei = _BACKEND / pfad
        assert datei.exists(), f"Ausnahme zeigt ins Leere: {pfad}"
        assert _ROH_ZUGRIFF.search(datei.read_text(encoding="utf-8")), (
            f"{pfad} steht als Ausnahme, trägt aber keinen Roh-Zugriff mehr — "
            f"Eintrag löschen, sonst deckt er künftig einen echten Treffer."
        )


def test_der_zehn_kwh_default_ist_nirgends_zurueck():
    """N127 wortwörtlich: kein `KAPAZITAET_KWH`-Lesezugriff mit Default 10."""
    muster = re.compile(r'KAPAZITAET_KWH"\s*\]\s*,\s*10\s*\)')
    treffer = [
        str(p.relative_to(_BACKEND))
        for p in _BACKEND.rglob("*.py")
        if "tests" not in p.parts and muster.search(p.read_text(encoding="utf-8"))
    ]
    assert treffer == [], f"10-kWh-Default zurück in: {treffer}"


def _funktions_koerper(quelle: str, name: str) -> str:
    """Code einer Top-Level-Funktion **ohne** Docstring und ohne Nachbarn.

    Seit A31-2 stehen zwei Kapazitäts-Helper in derselben Datei; ein Schnitt
    nur am `def` würde den Nachbarn mitlesen und die Zusicherungen unten still
    entwerten (der Netto-Helper *darf* `NUTZBARE_KAPAZITAET_KWH` enthalten).
    """
    rumpf = quelle.split(f"def {name}(")[1]
    rumpf = re.split(r"\n(?=def |@)", rumpf)[0]
    return rumpf.split('"""')[2] if '"""' in rumpf else rumpf


def test_helper_traegt_die_regel_noch():
    """Gegenprobe wie bei P3-a: die Zusicherungen stehen im Quelltext, nicht nur
    im Test. Ein späterer „Verbesserer", der einen Netto- oder Spalten-Fallback
    einbaut, ändert genau diese Datei."""
    quelle = (_BACKEND / "core/investition_kennwerte.py").read_text(encoding="utf-8")
    brutto = _funktions_koerper(quelle, "get_speicher_kapazitaet_kwh")
    # Genau eine Quelle: das parameter-JSON, Schlüssel aus dem Kanon.
    assert 'PARAM_SPEICHER["KAPAZITAET_KWH"]' in brutto
    assert "NUTZBARE_KAPAZITAET_KWH" not in brutto, (
        "Netto-Fallback im Brutto-Helper — brutto und netto sind zwei Zahlen. "
        "Die erlaubte Richtung ist netto → brutto und steht im NETTO-Helper."
    )
    assert "leistung_kwp" not in brutto, (
        "Spalten-Fallback im Helper-Körper — s. test_kein_fallback_auf_die_mehrzweck_spalte"
    )
    # Der seit A31-2 geteilte Körper darf ebenfalls keinen Fallback tragen —
    # sonst wanderte die Regelverletzung eine Ebene tiefer und beide Helper
    # bekämen sie stillschweigend mit.
    geteilt = _funktions_koerper(quelle, "_speicher_param_kwh")
    assert "NUTZBARE_KAPAZITAET_KWH" not in geteilt and "leistung_kwp" not in geteilt, (
        "Fallback im geteilten Körper `_speicher_param_kwh` — er liest EINEN "
        "übergebenen Schlüssel und sonst nichts."
    )
