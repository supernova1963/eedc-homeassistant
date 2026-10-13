"""#427 Punkt 2 (Melder rapahl, Entscheid Gernot 13.10.2026) — die Netzladung des Speichers im laufenden Monat aus den Tagen.

**Befund (HEAD 81ee0672):** *Cockpit → Monat* las ``speicher_ladung_netz_kwh`` nur aus der gespeicherten Monatszeile
(``aktueller_monat/komponenten.py``, Tor ``"speicher" in typen_mit_zeile``). Der laufende Monat hat nie eine Zeile ⇒ die
Kachel „Batterieladung Netz" und die Zeile „davon aus dem Netz (Arbitrage)" fehlten, obwohl *Cockpit → Tag* den Wert je
Tag nannte (Boundary-Differenz, Fenster [Vortag 23:00, 23:00)).

**Regel seit dem Bau:** (a) im laufenden Monat ohne Speicher-Zeile die Σ der abgelaufenen Tage über den Bereichs-Leser
— dieselbe Boundary-Differenz und dasselbe Fenster wie der Tag; kein neuer Tagesschlüssel, kein Nachfüllen alter Tage;
(b) Preis wie der Tag (TEP-gewichtet, ``berechne_effektiver_ladepreis``); (c) das Tor kennt „aus Tagen", die Herkunft
steht in ``speicher_ladung_netz_herkunft`` (``"tageswerte"``). Ein abgeschlossener Monat ohne Zeile bleibt leer
(Monatsabschluss, N-675).

Die Form ist ``M04`` der Achsen-Matrix: Akku A lädt 0,5 kWh/h von 2 bis 4 Uhr aus dem Netz (1,0 kWh je Tag), der
Preissensor nennt dort 25 ct. Die Uhr steht auf 04.07.2026 00:30 — drei abgelaufene Julitage.

Schwesterdateien: ``test_achsen_matrix.py`` (Zellen ``M04``/``speicher``, ``OHNE-ABSCHLUSS``), ``test_v2h_tageswert.py``
(dasselbe Päckchen).
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

JULI_TAGE = [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)]


async def _messe(weg: str, form_id: str = "M04") -> dict:
    """Cockpit → Monat (Juli laufend, Juni abgeschlossen ohne Abschluss) und Cockpit → Tag je Julitag."""
    import backend.api.routes.aktueller_monat as amr
    from backend.api.routes.energie_profil.tag import get_tag_detail

    form = am.MATRIX_FORMEN[form_id]
    verz = tempfile.mkdtemp(prefix="eedc-427-test-")
    try:
        engine, db = await mx._neue_db(f"{verz}/{weg}.db")
        try:
            aid, ids = await am.seed_anlage(db, form)
            svc = am.seed_ha(form) if weg == "HA" else mx._ha_aus()
            if weg == "SA":
                await am.seed_snapshots(db, form, aid, ids)
            with am.umgebung(form, svc):
                if weg == "HA":
                    await mx.fuelle_spiegel(engine, aid, svc)
                await mx.aggregiere_tage(db, form.pvform, aid, am.TAGE_JUNI + am.TAGE_JULI)
                juli = await amr.get_aktueller_monat(anlage_id=aid, jahr=2026, monat=7, db=db)
                juni = await amr.get_aktueller_monat(anlage_id=aid, jahr=2026, monat=6, db=db)
                tage = [(await get_tag_detail(anlage_id=aid, datum=t, db=db)).speicher_ladung_netz_kwh
                        for t in JULI_TAGE]
            return {"juli": juli, "juni": juni, "tage": tage}
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("weg", ["HA", "SA"])
async def test_laufender_monat_traegt_die_netzladung_aus_den_tagen(weg):
    m = await _messe(weg)
    juli = m["juli"]
    assert m["tage"] == [pytest.approx(1.0)] * 3, "Cockpit → Tag nennt je Tag 1,0 kWh"
    assert juli.speicher_ladung_netz_kwh == pytest.approx(sum(m["tage"])) == pytest.approx(3.0)
    assert juli.speicher_ladung_netz_herkunft == "tageswerte"


@pytest.mark.parametrize("weg, quelle, preis", [("HA", "tep", 25.0), ("SA", "bezugspreis", 30.0)])
async def test_preis_und_kosten_wie_der_tag(weg, quelle, preis):
    """(b) Preis wie der Tag — derselbe Helfer (``berechne_effektiver_ladepreis``, TEP-gewichtet), dieselbe Kette.
    Mit HA: Netzladung nur 2–4 Uhr, dort nennt der Preissensor 25 ct ⇒ 3,0 kWh × 25 ct = 0,75 €. Ohne HA kennt die
    Stundenzeile keinen Preis (``datenbasis-zu-duenn``) ⇒ die Kette fällt auf den Bezugspreis (30 ct ⇒ 0,90 €)."""
    juli = (await _messe(weg))["juli"]
    assert juli.speicher_ladung_netz_preis_quelle == quelle
    assert juli.speicher_ladung_netz_preis_cent == pytest.approx(preis, abs=0.01)
    assert juli.speicher_ladung_netz_kosten_euro == pytest.approx(3.0 * preis / 100, abs=0.005)


async def test_abgeschlossener_monat_ohne_zeile_bleibt_leer():
    """Juni ist vorbei, aber nicht abgeschlossen: eine Teilmenge der Tage wäre dort eine stille Untertreibung —
    die Antwort ist der Monatsabschluss (N-675). Unverändert ``None``, keine Herkunft."""
    juni = (await _messe("HA"))["juni"]
    assert juni.speicher_ladung_netz_kwh is None
    assert juni.speicher_ladung_netz_herkunft is None


async def test_ohne_netzlade_zaehler_keine_kachel():
    """M02: ein Speicher ohne Netzlade-Zähler — der Bereichs-Leser findet nichts, die Kachel bleibt aus (keine 0)."""
    juli = (await _messe("HA", "M02"))["juli"]
    assert juli.speicher_ladung_netz_kwh is None
    assert juli.speicher_ladung_netz_herkunft is None
