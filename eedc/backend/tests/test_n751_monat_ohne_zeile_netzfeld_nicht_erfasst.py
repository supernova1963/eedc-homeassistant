"""N-751 (16.10.2026) — ein Monat OHNE Monatszeile, dessen Netzfeld kein Tag erfasst hat, ist «nicht erfasst», keine 0.

Bis dahin füllte ``monats_fakten/bau.py::_zaehler_fakten`` ohne Zeile beide Netzfelder aus der Tagesebene und las deren
Marken nicht (``TagesMonatsSumme.einspeisung_erfasst``/``netzbezug_erfasst``, N-585): eine Anlage ohne Einspeisungs-Sensor
stand in *Cockpit → Jahr* (Monatsliste und Verlauf, ``inkl_nur_tageswerte``) mit Einspeisung 0, Eigenverbrauchsquote 100 %
und der Ersparnis auf die ganze PV da — gemessen am HEAD 893af648 an diesem Fall: Quote 100,0 %, Autarkie 94,8 %,
Ersparnis 16,5 € —, während der Kopf derselben Seite (faltet *Cockpit → Monat*, N-585-Marken) den Monat als nicht erfasst
führte. Seit N-751 übernimmt die Schicht ohne Zeile die Marken der Tagesebene (ein nicht erfasstes Feld bleibt 0,0 in der
Zahl mit Flag ``False``, wie N-736 mit Zeile), und die Monatsliste nimmt den Monat aus der Bilanz (``_ohne_netz_bilanz``).
``meta.netz_erfasst`` bleibt «Zählerzeile UND beide Felder erfasst» (``hat_zaehlerzeile`` unverändert).

Fixture wie ``test_n121_monate_ohne_db_spur.py`` (Juli 2026 nur als Tagesebene, zwei Tage); Uhr der Matrix
(``pv_achse_matrix._FesteUhr``, 04.07.2026 00:30 — Juli ist der laufende Monat, *Cockpit → Monat* liest die Tagesebene).
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.monats_fakten import TAGESWERT_ZAEHLER, lade_monats_fakten
from backend.tests import factories
from backend.tests import pv_achse_matrix as mx

#: Die Felder, die die Liste für einen nicht erfassten Monat leer lässt (Auswahl der Anzeige von Cockpit → Jahr).
_LEER = ("eigenverbrauch_kwh", "eigenverbrauchsquote_prozent", "autarkie_prozent", "ev_ersparnis_euro",
         "einspeisung_kwh", "netzbezug_kwh", "netto_ertrag_euro")


async def _juli_nur_tage(db, *, einspeisung: bool, netzbezug: bool):
    """Juli 2026 nur als Tagesebene, zwei Tage (PV 30/25); Einspeisung bzw. Netzbezug nur, wenn ein Sensor sie misst."""
    anlage = await factories.anlage(db, anlagenname="N-751", standort_land="DE")
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0))
    await db.flush()
    for tag, pv, einsp, netz in ((date(2026, 7, 1), 30.0, 20.0, 1.0), (date(2026, 7, 2), 25.0, 15.0, 2.0)):
        db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=tag, komponenten_kwh={"pv_1": pv}))
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=12, pv_kw=pv, verbrauch_kw=0.0,
            einspeisung_kw=einsp if einspeisung else None, netzbezug_kw=netz if netzbezug else None,
        ))
    await db.commit()
    return anlage


async def _juli_fakt(db, aid):
    return next(f for f in await lade_monats_fakten(db, aid, inkl_nur_tageswerte=True) if f.schluessel == (2026, 7))


async def _juli_zeile(db, aid):
    zeilen = await list_monatsdaten_aggregiert(anlage_id=aid, jahr=2026, inkl_ohne_zaehlerzeile=True,
                                               inkl_nur_tageswerte=True, db=db)
    return next(z for z in zeilen if z.monat == 7)


def _uhr() -> ExitStack:
    import backend.api.routes.aktueller_monat as am

    st = ExitStack()
    st.enter_context(patch.object(am, "datetime", mx._FesteUhr))
    st.enter_context(patch("backend.services.kanal.bilanz_leser.uhr", lambda: int(mx.JETZT.timestamp())))
    return st


async def test_erfasst_bleibt_ein_messwert(db):
    """Gegenprobe (N-121 «erfasst ⇒ 35,0»): beide Sensoren ⇒ Zahl aus den Stundenzeilen, beide Flags True; ``netz_erfasst``
    bleibt ohne Zeile False (es schließt die Zählerzeile ein); die Liste nennt Eigenverbrauch und Quote."""
    a = await _juli_nur_tage(db, einspeisung=True, netzbezug=True)
    f = await _juli_fakt(db, a.id)
    assert (f.zaehler.einspeisung_kwh, f.zaehler.netzbezug_kwh) == (35.0, 3.0)
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst) == (True, True)
    assert (f.meta.hat_zaehlerzeile, f.meta.netz_erfasst) == (False, False)
    assert TAGESWERT_ZAEHLER in f.meta.tageswert_gruppen
    z = await _juli_zeile(db, a.id)
    assert (z.einspeisung_kwh, z.netzbezug_kwh, z.eigenverbrauch_kwh) == (35.0, 3.0, 20.0)
    assert z.eigenverbrauchsquote_prozent == pytest.approx(36.4, abs=0.05)


async def test_ohne_einspeisungs_sensor_nicht_erfasst(db):
    """**N-751.** Ohne Einspeisungs-Sensor: Flag False, die Zahl bleibt 0,0; die Liste nennt weder Eigenverbrauch noch
    Quote, Autarkie oder Ersparnis (am HEAD: 100,0 % / 94,8 % / 16,5 €). PV bleibt sichtbar."""
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=True)
    f = await _juli_fakt(db, a.id)
    assert f.zaehler.einspeisung_kwh == 0.0                     # ZaehlerFakten bleibt float
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst, f.meta.netz_erfasst) == (False, True, False)
    z = await _juli_zeile(db, a.id)
    assert z.pv_erzeugung_kwh == 55.0
    for feld in _LEER:
        assert getattr(z, feld) is None, feld


async def test_ohne_netz_sensoren_nicht_erfasst(db):
    """Ohne jeden Netz-Sensor (Balkonkraftwerk): am HEAD Quote und Autarkie 100 % — jetzt nichts."""
    a = await _juli_nur_tage(db, einspeisung=False, netzbezug=False)
    f = await _juli_fakt(db, a.id)
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst) == (False, False)
    z = await _juli_zeile(db, a.id)
    assert z.pv_erzeugung_kwh == 55.0
    for feld in _LEER:
        assert getattr(z, feld) is None, feld


@pytest.mark.parametrize("einspeisung,netzbezug", [(False, True), (False, False), (True, True)])
async def test_kopf_und_monatsliste_von_cockpit_jahr_stimmen_ueberein(db, einspeisung, netzbezug):
    """Kopf (faltet *Cockpit → Monat*) und Monatsliste derselben Seite nennen für den Monat dieselbe Bilanz.

    ⚑ Nicht verglichen: das ERFASSTE Netzfeld eines teilweise erfassten Monats — die Liste lässt nach der Regel von N-736
    (ein Netzfeld nicht erfasst ⇒ beide Netzfelder, Bilanz und Geld «–») auch den gemessenen Netzbezug leer, der Kopf
    nennt ihn (3,0 kWh im Fall ohne Einspeisungs-Sensor)."""
    from backend.services.jahres_aggregat import baue_jahr

    a = await _juli_nur_tage(db, einspeisung=einspeisung, netzbezug=netzbezug)
    with _uhr():
        j = await baue_jahr(db, a.id, 2026, heute=mx.JETZT.date())
    kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
    z = await _juli_zeile(db, a.id)
    for k_feld, z_feld in (("eigenverbrauch_kwh", "eigenverbrauch_kwh"), ("autarkie_prozent", "autarkie_prozent"),
                           ("einspeisung_kwh", "einspeisung_kwh"), ("ev_ersparnis_euro", "ev_ersparnis_euro"),
                           ("netto_ertrag_euro", "netto_ertrag_euro")):
        k, w = kopf.get(k_feld), getattr(z, z_feld)
        assert (k is None) == (w is None), (k_feld, k, w)
        if k is not None:
            assert k == pytest.approx(w, abs=0.05), (k_feld, k, w)
