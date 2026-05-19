"""
Akzeptanztests für den `ist_aktiv_im_monat`-Filter und seine Anwendung in
Read-Sites (#236 detLAN).

Geprüft:
  1. Helper-Verhalten — anschaffungsdatum + stilllegungsdatum (Eckfälle)
  2. Integration: /api/monatsdaten/aggregiert/{anlage_id} aggregiert keine
     IMDs aus Monaten vor anschaffungsdatum (Hauptbefund #236)
"""

from __future__ import annotations

from datetime import date

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


# ── Helper-Tests ────────────────────────────────────────────────────────────


def test_ist_aktiv_im_monat_ohne_grenzen():
    """Ohne anschaffungs- und stilllegungsdatum: immer aktiv."""
    inv = Investition(anschaffungsdatum=None, stilllegungsdatum=None)
    assert inv.ist_aktiv_im_monat(2024, 1) is True
    assert inv.ist_aktiv_im_monat(2026, 12) is True


def test_ist_aktiv_im_monat_vor_anschaffung():
    """Monate vor anschaffungsdatum.month: nicht aktiv. Anschaffungsmonat selbst: aktiv."""
    inv = Investition(anschaffungsdatum=date(2025, 4, 15), stilllegungsdatum=None)
    assert inv.ist_aktiv_im_monat(2025, 3) is False, "März vor April-Anschaffung"
    assert inv.ist_aktiv_im_monat(2025, 4) is True, "April-Anschaffungsmonat (Tag-15 im Monat)"
    assert inv.ist_aktiv_im_monat(2025, 5) is True
    assert inv.ist_aktiv_im_monat(2024, 12) is False
    assert inv.ist_aktiv_im_monat(2025, 1) is False


def test_ist_aktiv_im_monat_nach_stilllegung():
    """Monate nach stilllegungsdatum.month: nicht aktiv. Stilllegungsmonat selbst: aktiv."""
    inv = Investition(
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=date(2025, 8, 15),
    )
    assert inv.ist_aktiv_im_monat(2025, 7) is True
    assert inv.ist_aktiv_im_monat(2025, 8) is True, "Stilllegungsmonat zählt teilweise"
    assert inv.ist_aktiv_im_monat(2025, 9) is False, "September nach Aug-Stilllegung"


def test_monatsbericht_hat_flags_filtern_vor_anschaffung():
    """#239 detLAN-Folge zu #236: hat_*-Flags im Monatsbericht müssen pro
    Monat nach anschaffungsdatum filtern, nicht pro Anlage.

    Sonst rendert MonatsabschlussView.tsx die WP-Sektion auch in Monaten
    vor Anschaffung (alle Werte "—") — genau das, was detLAN als P2 in
    #236 monierte. Spiegelt die Logik aus aktueller_monat.py:1101+.
    """
    wp_april = Investition(typ="waermepumpe", anschaffungsdatum=date(2025, 4, 1))
    eauto_april = Investition(
        typ="e-auto", anschaffungsdatum=date(2025, 4, 1), parameter={}
    )
    speicher_alt = Investition(typ="speicher", anschaffungsdatum=date(2023, 1, 1))
    investitionen = [wp_april, eauto_april, speicher_alt]

    def _hat(typ: str, jahr: int, monat: int) -> bool:
        if typ in ("e-auto", "wallbox"):
            return any(
                i.typ == typ
                and not (i.parameter or {}).get("ist_dienstlich", False)
                and i.ist_aktiv_im_monat(jahr, monat)
                for i in investitionen
            )
        return any(
            i.typ == typ and i.ist_aktiv_im_monat(jahr, monat)
            for i in investitionen
        )

    assert _hat("waermepumpe", 2025, 3) is False, "März darf WP-Sektion nicht zeigen"
    assert _hat("waermepumpe", 2025, 4) is True, "April muss WP-Sektion zeigen"
    assert _hat("e-auto", 2025, 3) is False, "März darf E-Auto-Sektion nicht zeigen"
    assert _hat("e-auto", 2025, 4) is True, "April muss E-Auto-Sektion zeigen"
    assert _hat("speicher", 2025, 3) is True, "Speicher (seit 2023) muss in März zeigen"


def test_ist_aktiv_im_monat_kombiniert():
    """Anschaffungs- und Stilllegungsdatum gemeinsam — Sandwich-Test."""
    inv = Investition(
        anschaffungsdatum=date(2025, 4, 10),
        stilllegungsdatum=date(2026, 2, 28),
    )
    assert inv.ist_aktiv_im_monat(2025, 3) is False
    assert inv.ist_aktiv_im_monat(2025, 4) is True
    assert inv.ist_aktiv_im_monat(2025, 12) is True
    assert inv.ist_aktiv_im_monat(2026, 2) is True
    assert inv.ist_aktiv_im_monat(2026, 3) is False


# ── Integration: /aggregiert/{anlage_id} respektiert Anschaffungsdatum ──────


async def test_aggregiert_endpoint_ignoriert_vor_anschaffungs_imd(db):
    """detLAN-Hauptbefund #236 — Drift-Symptom-Test.

    Setup: Anlage seit 2024. WP-Investition mit Anschaffung April 2025.
    Test-Daten:
      - IMD März 2025 (vor Anschaffung) für die WP: strom=100, waerme=400
      - IMD April 2025 (Anschaffungsmonat) für die WP: strom=80, waerme=320
    Erwartet: Aggregiert pro Monat — März WP-Werte = None (Komponente
    in dem Monat nicht aktiv, nicht "echte 0"; CLAUDE.md-Linie 0 ≠ None),
    April WP-Werte = 80/320.
    """
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    anlage = Anlage(anlagenname="TestAnlage", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    for monat in (3, 4):
        db.add(Monatsdaten(
            anlage_id=anlage.id,
            jahr=2025, monat=monat,
            netzbezug_kwh=200.0, einspeisung_kwh=50.0,
        ))

    wp = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Test-WP",
        anschaffungsdatum=date(2025, 4, 1),
    )
    db.add(wp)
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=3,
        verbrauch_daten={"stromverbrauch_kwh": 100, "heizenergie_kwh": 400},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=4,
        verbrauch_daten={"stromverbrauch_kwh": 80, "heizenergie_kwh": 320},
    ))
    await db.commit()

    result = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=None, db=db,
    )
    by_monat = {(r.jahr, r.monat): r for r in result}

    maerz = by_monat.get((2025, 3))
    april = by_monat.get((2025, 4))

    assert maerz is not None, "März-Monatsdaten erwartet"
    assert april is not None, "April-Monatsdaten erwartet"
    assert maerz.wp_strom_kwh is None, (
        f"März WP-Strom muss None sein (Komponente nicht aktiv, nicht 'echte 0'), "
        f"war {maerz.wp_strom_kwh!r}"
    )
    assert maerz.wp_heizung_kwh is None, (
        f"März WP-Heizung muss None sein, war {maerz.wp_heizung_kwh!r}"
    )
    assert april.wp_strom_kwh == 80, (
        f"April WP-Strom muss 80 sein (Wert aus IMD), war {april.wp_strom_kwh!r}"
    )
    assert april.wp_heizung_kwh == 320, (
        f"April WP-Heizung muss 320 sein, war {april.wp_heizung_kwh!r}"
    )


async def test_aggregiert_endpoint_echte_null_unterscheidet_sich_von_none(db):
    """CLAUDE.md-Linie 0 ≠ None — IMD mit Wert 0 (z.B. Heizung im Sommer)
    muss als 0 ausgespielt werden, nicht als None."""
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    anlage = Anlage(anlagenname="TestAnlage", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=7,
        netzbezug_kwh=80.0, einspeisung_kwh=200.0,
    ))

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Test-WP", anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wp)
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=7,
        verbrauch_daten={
            "stromverbrauch_kwh": 30,
            "heizenergie_kwh": 0,        # echte 0!
            "warmwasser_kwh": 90,
        },
    ))
    await db.commit()

    result = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=None, db=db,
    )
    juli = next(r for r in result if r.monat == 7)

    assert juli.wp_strom_kwh == 30, (
        f"WP-Strom muss 30 sein (Wert vorhanden), war {juli.wp_strom_kwh!r}"
    )
    assert juli.wp_heizung_kwh == 0, (
        f"WP-Heizung muss 0 sein (echte 0, IMD vorhanden), war {juli.wp_heizung_kwh!r}"
    )
    assert juli.wp_warmwasser_kwh == 90, (
        f"WP-Warmwasser muss 90 sein, war {juli.wp_warmwasser_kwh!r}"
    )
