"""R15-2 (Rainer-PN #88625): Ø-Ladepreis-Vorschlag im Monatsabschluss-Wizard.

Das IMD-Feld `speicher_ladepreis_cent` war reine Handeingabe. Der
VorschlagService liefert jetzt einen BERECHNUNG-Vorschlag aus dem
stundengewichteten effektiven Ladepreis (#264 Etappe C) — überschreibbar,
bei Rechnungserhalt wird der finale Wert eingetragen.
"""

from __future__ import annotations

import pytest

from backend.models import Anlage, Investition
from backend.services.vorschlag_service import VorschlagQuelle, VorschlagService
from backend.services.speicher_wirtschaftlichkeit import EffektiverLadepreisErgebnis
import backend.services.speicher_wirtschaftlichkeit as sw


def _ergebnis(preis, quelle, mit_preis=20, gesamt=20):
    return EffektiverLadepreisErgebnis(
        quelle=quelle,
        effektiver_ladepreis_cent=preis,
        netz_lade_kwh=31.6,
        netzlade_stunden_mit_preis=mit_preis,
        netzlade_stunden_gesamt=gesamt,
        stunden_gesamt_im_fenster=720,
    )


async def _seed(db) -> tuple[int, int]:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="BYD",
        parameter={"kapazitaet_kwh": 15.4, "arbitrage_faehig": True, "laedt_aus_netz": True},
    )
    db.add(inv)
    await db.flush()
    return anlage.id, inv.id


async def test_ladepreis_vorschlag_aus_tep(db, monkeypatch):
    """Belastbare TEP-Quelle → BERECHNUNG-Vorschlag mit Konfidenz 90 (über Vormonat)."""
    anlage_id, inv_id = await _seed(db)

    async def fake(*args, **kwargs):
        return _ergebnis(23.47, "dyn-tarif")

    monkeypatch.setattr(sw, "berechne_effektiver_ladepreis", fake)
    vorschlaege = await VorschlagService(db).get_vorschlaege(
        anlage_id, "speicher_ladepreis_cent", 2026, 6, investition_id=inv_id,
    )
    berechnet = [v for v in vorschlaege if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert len(berechnet) == 1
    assert berechnet[0].wert == pytest.approx(23.47)
    assert berechnet[0].konfidenz == 90
    # Höchste Konfidenz → steht vorn (FeldInput zeigt vorschlaege[0] als Placeholder)
    assert vorschlaege[0].quelle == VorschlagQuelle.BERECHNUNG


async def test_ladepreis_vorschlag_duenne_datenbasis_niedrige_konfidenz(db, monkeypatch):
    anlage_id, inv_id = await _seed(db)

    async def fake(*args, **kwargs):
        return _ergebnis(21.0, "datenbasis-zu-duenn", mit_preis=5, gesamt=20)

    monkeypatch.setattr(sw, "berechne_effektiver_ladepreis", fake)
    vorschlaege = await VorschlagService(db).get_vorschlaege(
        anlage_id, "speicher_ladepreis_cent", 2026, 6, investition_id=inv_id,
    )
    berechnet = [v for v in vorschlaege if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert len(berechnet) == 1
    assert berechnet[0].konfidenz == 55
    assert "25 % Abdeckung" in berechnet[0].beschreibung


async def test_ladepreis_ohne_tep_kein_berechnungs_vorschlag(db, monkeypatch):
    anlage_id, inv_id = await _seed(db)

    async def fake(*args, **kwargs):
        return _ergebnis(None, "keine-tep-daten", mit_preis=0, gesamt=0)

    monkeypatch.setattr(sw, "berechne_effektiver_ladepreis", fake)
    vorschlaege = await VorschlagService(db).get_vorschlaege(
        anlage_id, "speicher_ladepreis_cent", 2026, 6, investition_id=inv_id,
    )
    assert not [v for v in vorschlaege if v.quelle == VorschlagQuelle.BERECHNUNG]


async def test_ladepreis_helper_fehler_bricht_wizard_nicht(db, monkeypatch):
    """Vorschlag ist optional — Exception im Helper darf get_vorschlaege nie brechen."""
    anlage_id, inv_id = await _seed(db)

    async def kaputt(*args, **kwargs):
        raise RuntimeError("TEP kaputt")

    monkeypatch.setattr(sw, "berechne_effektiver_ladepreis", kaputt)
    vorschlaege = await VorschlagService(db).get_vorschlaege(
        anlage_id, "speicher_ladepreis_cent", 2026, 6, investition_id=inv_id,
    )
    assert not [v for v in vorschlaege if v.quelle == VorschlagQuelle.BERECHNUNG]
