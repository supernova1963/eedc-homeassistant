"""Differentielles Charakterisierungs-Netz für die WP-Alternativkosten-Ersparnis
im Aussichten-Finanzpfad (`get_finanz_prognose`), vor der Konvergenz auf den
SoT-Helper `core/berechnungen/alternativkosten.berechne_wp_alternativkosten_ersparnis`.

Die „bisherige" WP-vs-Gas/Öl-Ersparnis-Formel lag dupliziert in `ha_export.py`
(bereits auf den Helper konvergiert) UND hier inline (Z. ~1303–1334) — gleiche
Drift-Klasse. Bestand: `test_aussichten_multi_wp.py` testet die Formel nur als
Smoke (`>= 0` / `is not None`), nicht den Wert.

Pin-Methode: das Delta von `bisherige_ertraege_euro` MIT vs. OHNE die WP
isoliert exakt `bisherige_wp_ersparnis` (Finanz-/EV-Apparat aus den Monatsdaten
kürzt sich weg — er hängt nicht an der WP-Investition). Verhaltensneutral: nach
der Konvergenz muss das Delta byte-identisch bleiben.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten

# Zwei erfasste Monate; Default-Tarif (netzbezug 30 ct), Gas-WP wirkungsgrad 0,90,
# PV-Anteil 0,5. Pro Monat: thermisch 1000 kWh, WP-Netzstrom 300 kWh, Gaspreis 10 ct.
_MONATE = [(2026, 1), (2026, 2)]


async def _seed(db, *, mit_wp: bool) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # Monatsdaten ohne Einspeisung/Netzbezug → Finanz-/EV-Apparat liefert in
    # beiden Läufen denselben Beitrag und kürzt sich im Delta weg.
    for (j, m) in _MONATE:
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=j, monat=m,
            netzbezug_kwh=0.0, einspeisung_kwh=0.0, gaspreis_cent_kwh=10.0,
        ))
    if mit_wp:
        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP-Gas",
            anschaffungsdatum=date(2025, 1, 1),
            betriebskosten_jahr=0.0,
            parameter={
                "alter_energietraeger": "gas",
                "alter_preis_cent_kwh": 12.0,
                "alternativ_zusatzkosten_jahr": 120.0,
            },
        )
        db.add(wp)
        await db.flush()
        for (j, m) in _MONATE:
            db.add(InvestitionMonatsdaten(
                investition_id=wp.id, jahr=j, monat=m,
                verbrauch_daten={
                    "heizenergie_kwh": 800.0,
                    "warmwasser_kwh": 200.0,
                    "stromverbrauch_kwh": 300.0,
                },
            ))
    await db.flush()
    return anlage.id


async def test_wp_alternativkosten_delta_isoliert(db):
    """Delta bisherige_ertraege (mit−ohne WP) == bisherige WP-Ersparnis.

    Hand-Rechnung pro Monat:
      gas_kosten        = (1000 / 0,90) * 10 / 100 = 111,111 €
      wp_stromkosten    = 300 * (1−0,5) * 30 / 100 =  45,000 €
      monats_ersparnis  =                            66,111 €
    zwei Monate = 132,222 €; fixe Zusatzkosten 120 * 2/12 = 20 € → 152,22 €.
    (Monats-Gaspreis 10 ct aus Monatsdaten überstimmt den WP-Default 12 ct.)
    """
    id_ohne = await _seed(db, mit_wp=False)
    id_mit = await _seed(db, mit_wp=True)

    res_ohne = await get_finanz_prognose(anlage_id=id_ohne, monate=12, db=db)
    res_mit = await get_finanz_prognose(anlage_id=id_mit, monate=12, db=db)

    delta = res_mit.bisherige_ertraege_euro - res_ohne.bisherige_ertraege_euro
    assert delta == pytest.approx(152.22, abs=0.01)


async def test_wp_forecast_ersparnis_golden(db):
    """Golden-Master für den WP-PROGNOSE-Pfad (`wp_alternativ_ersparnis_euro`),
    der die Gaskosten-Teilformel inline trägt. Ohne WP ist der Wert 0 → der
    Forecast-Wert ist hier isoliert. Pinnt den IST-Stand vor der Migration auf
    `gas_kosten_altanlage` (byte-identische Arithmetik → unverändert)."""
    id_mit = await _seed(db, mit_wp=True)
    res = await get_finanz_prognose(anlage_id=id_mit, monate=12, db=db)
    # 12-Monats-Horizont deckt jeden Kalendermonat genau einmal ab →
    # Saison-Summen datums-unabhängig, Golden-Wert stabil.
    assert res.wp_alternativ_ersparnis_euro == pytest.approx(971.83, abs=0.01)
