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

Bewusst **kein baumweiter Wächter**: die Dateiliste unten ist eine Regression
über die namentlich migrierten Stellen. Ein echter Wächter für die
Kapazitäts-Leseregel braucht Baseline 0, und die gibt es erst, wenn A31-2 die
drei verbliebenen Brutto-mit-Netto-Fallback-Konstrukte aufgelöst hat
(`api/routes/ha_export.py`, `investitionen/crud.py`, `investitionen/dashboards.py`
— sie stehen unten als benannte Ausnahmen). Der Wächter ist A31-3.
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
# 3. Regression über die migrierten Stellen (kein Wächter — s. Modul-Docstring)
# ============================================================================

_BACKEND = Path(__file__).resolve().parent.parent

# Die 13 in A31-1 migrierten Lesestellen. Fällt eine zurück auf den
# Literal-/Kanon-Zugriff, ist der Helper nicht mehr SoT.
_MIGRIERTE_DATEIEN = [
    "services/pdf/builders/jahresbericht.py",
    "services/energie_profil/tage_werte.py",
    "services/daten_checker/stammdaten.py",
    "api/routes/aktueller_monat.py",
    "api/routes/cockpit/uebersicht.py",
    "services/ha_export_prognose.py",
    "api/routes/energie_profil/views.py",
    "api/routes/import_export/helpers.py",
    "services/community_service.py",
    "core/berechnungen/co2_amortisation.py",
]

# Zwei Dateien tragen migrierte Stellen UND je ein Brutto-mit-Netto-Fallback-
# Konstrukt, das erst A31-2 auflöst. Sie sind hier ausgenommen, damit die
# Ausnahme benannt ist statt stillschweigend zu fehlen.
_A31_2_OFFEN = {
    "api/routes/investitionen/crud.py": 1,
    "api/routes/investitionen/dashboards.py": 1,
    "api/routes/ha_export.py": 1,
}

_ROH_ZUGRIFF = re.compile(
    r'(get\(\s*"kapazitaet_kwh"|\[\s*"kapazitaet_kwh"\s*\]'
    r'|PARAM_SPEICHER\[\s*"KAPAZITAET_KWH"\s*\])'
)


def test_migrierte_stellen_lesen_die_kapazitaet_nicht_mehr_roh():
    treffer = {
        pfad: len(_ROH_ZUGRIFF.findall((_BACKEND / pfad).read_text(encoding="utf-8")))
        for pfad in _MIGRIERTE_DATEIEN
    }
    assert all(n == 0 for n in treffer.values()), (
        f"Roh-Zugriff zurück: { {p: n for p, n in treffer.items() if n} }"
    )


def test_die_a31_2_ausnahmen_sind_noch_da_und_nicht_mehr_geworden():
    """Verhindert beides: eine verwaiste Ausnahme (A31-2 hat aufgeräumt, die
    Zeile hier nicht) und eine neue Stelle, die sich hinter ihr versteckt."""
    for pfad, erwartet in _A31_2_OFFEN.items():
        n = len(_ROH_ZUGRIFF.findall((_BACKEND / pfad).read_text(encoding="utf-8")))
        assert n == erwartet, (
            f"{pfad}: {n} statt {erwartet} Rest-Zugriffe. Mehr = neue Stelle, "
            f"weniger = A31-2 ist durch und diese Ausnahme gehört gelöscht."
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


def test_helper_traegt_die_regel_noch():
    """Gegenprobe wie bei P3-a: die Zusicherungen stehen im Quelltext, nicht nur
    im Test. Ein späterer „Verbesserer", der einen Netto- oder Spalten-Fallback
    einbaut, ändert genau diese Datei."""
    quelle = (_BACKEND / "core/investition_kennwerte.py").read_text(encoding="utf-8")
    körper = quelle.split("def get_speicher_kapazitaet_kwh")[1]
    # Genau eine Quelle: das parameter-JSON, Schlüssel aus dem Kanon.
    assert 'PARAM_SPEICHER["KAPAZITAET_KWH"]' in körper
    assert "NUTZBARE_KAPAZITAET_KWH" not in körper.split('"""')[2], (
        "Netto-Fallback im Helper-Körper — brutto und netto sind zwei Zahlen"
    )
    assert "leistung_kwp" not in körper.split('"""')[2], (
        "Spalten-Fallback im Helper-Körper — s. test_kein_fallback_auf_die_mehrzweck_spalte"
    )
