"""§51 EEG-Abzug bei negativen Börsenpreisen — Berechnungs-Layer + DB-Service.

Hintergrund: Solarpaket I hat für Neuanlagen den Vergütungsausfall in
Negativpreis-Stunden eingeführt (rcmcronny Discussion #120, ~6 Wochen alt).
Daten-Fundament steht in `TagesZusammenfassung.einspeisung_neg_preis_kwh`,
wird hier in Erlös-Helper + DB-Aggregat angeschlossen.

Tests decken ab:
- Pure Berechnung `einspeise_erloes_euro` (Standard-Fälle + Edge-Cases)
- DB-Aggregat `get_neg_preis_einspeisung_monat` / `_jahr` (None-Pfad, Σ,
  Anlagen-Isolation, Monatsgrenzen)
- **Tagespfad** `neg_preis_einspeisung_tageswert` + seine drei Read-Sites
  (`baue_tage_werte`, Tagesliste, Monatsauswertung) — dasselbe Gate, seit
  2026-08-03 (rapahl-Meldung, Abschnitt am Dateiende)
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import einspeise_erloes_euro
from backend.api.routes.energie_profil.views import (
    get_monatsauswertung,
    get_tages_zusammenfassungen,
)
from backend.models import Anlage, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.einspeise_erloes_service import (
    get_neg_preis_einspeisung_jahr,
    get_neg_preis_einspeisung_monat,
    neg_preis_einspeisung_tageswert,
)
from backend.services.energie_profil.tage_werte import baue_tage_werte


# --- Pure-Berechnung: einspeise_erloes_euro ---------------------------------

def test_kein_negativpreis_voller_erloes():
    """`neg_preis_kwh=None` → unverändert, alte Berechnung greift."""
    result = einspeise_erloes_euro(
        einspeisung_kwh=1000.0, neg_preis_kwh=None, verguetung_ct_kwh=8.2
    )
    assert result.erloes_euro == 82.0
    assert result.nicht_vergueteter_erloes_euro == 0.0
    assert result.nicht_verguetete_kwh == 0.0


def test_null_negativpreis_voller_erloes():
    """`neg_preis_kwh=0` → identisch zu None-Pfad."""
    result = einspeise_erloes_euro(
        einspeisung_kwh=1000.0, neg_preis_kwh=0.0, verguetung_ct_kwh=8.2
    )
    assert result.erloes_euro == 82.0
    assert result.nicht_verguetete_kwh == 0.0


def test_teil_negativpreis_anteilig_abgezogen():
    """Σ Erlös + entgangener Erlös == alte ungekürzte Rechnung (Invariante)."""
    einspeisung, neg, vc = 1000.0, 120.0, 8.2
    result = einspeise_erloes_euro(einspeisung, neg, vc)
    assert result.erloes_euro == pytest.approx((1000 - 120) * 8.2 / 100)
    assert result.nicht_vergueteter_erloes_euro == pytest.approx(120 * 8.2 / 100)
    assert result.nicht_verguetete_kwh == 120.0
    # Erhaltungs-Invariante: voller Erlös rekonstruierbar.
    voll = einspeisung * vc / 100
    assert result.erloes_euro + result.nicht_vergueteter_erloes_euro == pytest.approx(voll)


def test_neg_groesser_als_einspeisung_wird_geklemmt():
    """Drift zwischen Monatsdaten und Tages-Aggregat darf nicht negativ machen."""
    result = einspeise_erloes_euro(
        einspeisung_kwh=100.0, neg_preis_kwh=150.0, verguetung_ct_kwh=8.0
    )
    assert result.erloes_euro == 0.0
    assert result.nicht_verguetete_kwh == 100.0
    assert result.nicht_vergueteter_erloes_euro == 8.0


def test_nullte_einspeisung_liefert_nulle():
    """Keine Einspeisung → keine Erlöse, kein §51-Abzug."""
    result = einspeise_erloes_euro(0.0, 50.0, 8.2)
    assert result.erloes_euro == 0.0
    assert result.nicht_verguetete_kwh == 0.0


def test_negative_einspeisung_robust():
    """Defensive: negative Einspeisung (Datenfehler) → 0, nicht ValueError."""
    result = einspeise_erloes_euro(-10.0, 5.0, 8.2)
    assert result.erloes_euro == 0.0
    assert result.nicht_verguetete_kwh == 0.0


# --- DB-Service: get_neg_preis_einspeisung_monat ----------------------------

async def _seed_anlage(db, *, unterliegt_eeg_51: bool = True) -> int:
    # Default True in diesen Service-Tests: sie prüfen die Summier-/Isolations-
    # Logik. Der §51-Gate (Flag False → None) hat einen eigenen Test unten.
    anlage = Anlage(
        anlagenname="Test", leistung_kwp=10.0, standort_land="DE",
        unterliegt_eeg_51=unterliegt_eeg_51,
    )
    db.add(anlage)
    await db.flush()
    return anlage.id


async def test_monat_ohne_eeg51_flag_liefert_none_trotz_aggregaten(db):
    """§51-Gate: Anlage ohne Flag (Default) → None, auch wenn Tages-Aggregate da sind."""
    anlage_id = await _seed_anlage(db, unterliegt_eeg_51=False)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 15),
        einspeisung_neg_preis_kwh=10.0,
    ))
    await db.flush()
    assert await get_neg_preis_einspeisung_monat(db, anlage_id, 2026, 3) is None
    assert await get_neg_preis_einspeisung_jahr(db, anlage_id, 2026) is None


async def test_monat_ohne_tages_aggregate_liefert_none(db):
    """Anwender ohne Strompreis-Sensor → None, Read-Sites nutzen alte Berechnung."""
    anlage_id = await _seed_anlage(db)
    result = await get_neg_preis_einspeisung_monat(db, anlage_id, 2026, 3)
    assert result is None


async def test_monat_mit_tagen_aber_alle_null_liefert_null_komma_null(db):
    """Tages-Aggregate vorhanden, aber kein Negativpreis im Monat → 0.0, nicht None."""
    anlage_id = await _seed_anlage(db)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 1),
        einspeisung_neg_preis_kwh=0.0,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 2),
        einspeisung_neg_preis_kwh=0.0,
    ))
    await db.flush()
    result = await get_neg_preis_einspeisung_monat(db, anlage_id, 2026, 3)
    assert result == 0.0


async def test_monat_summiert_alle_tage(db):
    """Σ über alle Tage des Monats."""
    anlage_id = await _seed_anlage(db)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 1),
        einspeisung_neg_preis_kwh=5.0,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 15),
        einspeisung_neg_preis_kwh=10.0,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 31),
        einspeisung_neg_preis_kwh=3.0,
    ))
    await db.flush()
    result = await get_neg_preis_einspeisung_monat(db, anlage_id, 2026, 3)
    assert result == 18.0


async def test_monat_isoliert_andere_monate_und_anlagen(db):
    """Σ nimmt nur den Ziel-Monat der Ziel-Anlage."""
    anlage_id = await _seed_anlage(db)
    andere_anlage = Anlage(anlagenname="Andere", leistung_kwp=5.0, standort_land="DE")
    db.add(andere_anlage)
    await db.flush()

    # Treffer (Anlage A, März)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 3, 15),
        einspeisung_neg_preis_kwh=10.0,
    ))
    # Falscher Monat (Anlage A, Februar)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 2, 28),
        einspeisung_neg_preis_kwh=99.0,
    ))
    # Falsche Anlage (B, März)
    db.add(TagesZusammenfassung(
        anlage_id=andere_anlage.id, datum=date(2026, 3, 15),
        einspeisung_neg_preis_kwh=77.0,
    ))
    await db.flush()
    result = await get_neg_preis_einspeisung_monat(db, anlage_id, 2026, 3)
    assert result == 10.0


async def test_jahr_summiert_ueber_alle_monate(db):
    """Jahres-Aggregat zieht über alle Tages-Zeilen."""
    anlage_id = await _seed_anlage(db)
    for monat, wert in [(2, 4.0), (3, 10.0), (12, 6.0)]:
        db.add(TagesZusammenfassung(
            anlage_id=anlage_id, datum=date(2026, monat, 15),
            einspeisung_neg_preis_kwh=wert,
        ))
    await db.flush()
    result = await get_neg_preis_einspeisung_jahr(db, anlage_id, 2026)
    assert result == 20.0


async def test_jahr_ohne_tages_aggregate_liefert_none(db):
    anlage_id = await _seed_anlage(db)
    result = await get_neg_preis_einspeisung_jahr(db, anlage_id, 2026)
    assert result is None


# --- Tagespfad: dasselbe Gate wie Monat/Jahr (2026-08-03) -------------------
#
# Der Tagespfad las `TagesZusammenfassung.einspeisung_neg_preis_kwh` roh und
# kürzte den Erlös damit auch bei Anlagen OHNE §51-Pflicht. Gemeldet von rapahl
# (2026-08-02): 45 kWh Einspeisung, 1,86 € statt ~3,7 €. Es ist derselbe Fehler,
# der für den Cockpit-Pfad bereits behoben und getestet ist
# (`test_cockpit_einspeise_neg_preis.py::test_ohne_eeg51_flag_kein_abzug_*`) —
# der Tages-Zwilling wurde damals nicht mitgezogen
# ([[feedback_aggregations_drift]]).


async def _seed_tag_mit_einspeisung(db, *, unterliegt_eeg_51: bool):
    """Ein Tag, 20 kWh Einspeisung, davon 15 kWh bei negativem Börsenpreis."""
    anlage = Anlage(
        anlagenname="§51-Tagespfad", leistung_kwp=10.0, standort_land="DE",
        unterliegt_eeg_51=unterliegt_eeg_51,
    )
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    tag = date(2026, 8, 2)
    db.add_all([
        TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=h,
            pv_kw=10.0, verbrauch_kw=0.0, einspeisung_kw=10.0, netzbezug_kw=0.0,
        )
        for h in (11, 12)
    ])
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=tag, stunden_verfuegbar=2,
        negative_preis_stunden=5, einspeisung_neg_preis_kwh=15.0,
    ))
    await db.flush()
    return anlage, tag


def test_tageswert_gate_pur():
    """Der Helfer entscheidet allein am Schalter — ohne Query."""
    ohne = Anlage(anlagenname="A", leistung_kwp=1.0, unterliegt_eeg_51=False)
    mit = Anlage(anlagenname="B", leistung_kwp=1.0, unterliegt_eeg_51=True)

    assert neg_preis_einspeisung_tageswert(ohne, 15.0) is None
    assert neg_preis_einspeisung_tageswert(mit, 15.0) == 15.0
    # Kein Messwert bleibt kein Messwert — auch mit Flag.
    assert neg_preis_einspeisung_tageswert(mit, None) is None


async def test_tagespfad_ohne_eeg51_flag_kuerzt_den_erloes_nicht(db):
    """Die gemeldete Klasse: Mitschrift vorhanden, §51-Pflicht nicht."""
    anlage, tag = await _seed_tag_mit_einspeisung(db, unterliegt_eeg_51=False)

    zeilen = await baue_tage_werte(db, anlage, tag, tag)

    assert len(zeilen) == 1
    z = zeilen[0]
    # 20 kWh × 8 ct = 1,60 € — ungekürzt.
    assert z.einspeise_erloes == pytest.approx(1.60, abs=0.01)
    # Ausweis-Spalte schweigt wie die Monatstabelle bei derselben Anlage.
    assert z.einspeisung_neg_preis_kwh is None
    # Die Stundenzahl bleibt Marktinfo und damit sichtbar.
    assert z.negative_preis_stunden == 5


async def test_tagespfad_mit_eeg51_flag_kuerzt_weiterhin(db):
    """Gegenprobe: mit Schalter greift der Abzug unverändert.

    Ausdrücklich **Regressionsschutz, kein Beweis**: in der Rot-Probe (Gate
    deaktiviert) bleibt dieser Test grün — er sichert nur, dass der Fix den
    berechtigten Abzug nicht mit weggeräumt hat. Die drei Geschwister oben
    fallen ohne Gate.
    """
    anlage, tag = await _seed_tag_mit_einspeisung(db, unterliegt_eeg_51=True)

    zeilen = await baue_tage_werte(db, anlage, tag, tag)

    z = zeilen[0]
    # Nur (20 − 15) kWh × 8 ct = 0,40 €.
    assert z.einspeise_erloes == pytest.approx(0.40, abs=0.01)
    assert z.einspeisung_neg_preis_kwh == pytest.approx(15.0)


async def test_tagesliste_und_monatsauswertung_gaten_die_ausweis_spalte(db):
    """Die beiden Ausweis-Stellen in `energie_profil/views.py` ziehen mit."""
    anlage_ohne, tag = await _seed_tag_mit_einspeisung(db, unterliegt_eeg_51=False)
    await db.commit()

    tage = await get_tages_zusammenfassungen(
        anlage_id=anlage_ohne.id, von=tag, bis=tag, db=db
    )
    assert tage[0].einspeisung_neg_preis_kwh is None
    assert tage[0].negative_preis_stunden == 5

    monat = await get_monatsauswertung(
        anlage_id=anlage_ohne.id, jahr=2026, monat=8, top_n=10, db=db
    )
    assert monat.einspeisung_neg_preis_kwh is None
    assert monat.negative_preis_stunden == 5
