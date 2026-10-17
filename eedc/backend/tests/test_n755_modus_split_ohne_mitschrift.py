"""N-755 (V-1, HA-Bauform S4-Nachlauf) — ein Monat ohne Abschluss, dessen WP-Gruppe die Kanäle decken, trägt die Aufteilung nach
Betriebsart auch für ein Gerät **ohne** Betriebsart-Mitschrift (Betriebsart nur in den Stundenzeilen).

**Befund (HEAD 0a4e852e, ebenso 1427eed4 und 32fcec9a — seit E4d/v4.1.3; Messskript
``plans/ha-bauform-werkzeug/fund-s4-nachlauf/v1_messung.py``):** im gedeckten Monat nahmen die Monats-Fakten
(``laden._ergaenze_modus_split_ohne_abschluss``), der HA-Export (``investition_sensoren._wp_nachtrag``) und Cockpit → Monat
(``quellen_leser._wp_aus_kanaelen`` → ``wp_aus_zeilen``) den Split nur aus dem abgeleiteten Kanal «Strom je Betriebsart».
Ein Gerät ohne Mitschrift hat keinen ⇒ Cockpit → Monat, Jahr, Übersicht und HA-Export ohne Aufteilung, während Cockpit →
Tag sie zeigte (6,6/0,6 je Tag). Betroffen sind nur Geräte, deren Betriebsart in den Stundenzeilen steht, die aber nie
einen Mitschrift-Kanal hatten — Monate VOR dem Beginn der Mitschrift wählen die WP-Gruppe ``bestand`` (gemessen, Variante
``ab0207``) und waren nie betroffen.

**Regel seit dem Bau** (``modus_split_monat.lade_modus_split_mit_kanaelen``, ``zeilen_mit_split_der_stundenzeilen``): im
gedeckten Monat je Gerät — mit abgeleitetem Kanal aus dem Kanal, ohne aus den Stundenzeilen (das Monats-Gegenstück zu
E-S4-3 H-2a ``kanal_stunden.modus_stunden_mit_rueckfall``).

Form: Achsen-Matrix M05 (WP 0,3 kWh/h, Etikett Heizen, 06–08 Uhr Warmwasser) mit einem WP-Leistungssensor in der
Stunden-Kurve (ohne ihn kennt die Stundenzeile keine WP-Menge und auch der Tag keinen Split); die Mitschrift wird beim
Tageslauf unterdrückt (Variante ``ohne``) bzw. beginnt am 02.07. (Gegenprobe).

Schwesterdateien: ``test_n727_ha_export_wp_modus_kanal.py`` (HA-Export = Übersicht), ``test_achsen_matrix.py`` (M05).
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from unittest.mock import patch

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

TAGE = am.TAGE_JUNI + am.TAGE_JULI


def _split(d: dict, praefix: str = "wp_modus_strom_") -> tuple:
    return tuple(round(d.get(f"{praefix}{k}_kwh") or 0.0, 2) for k in ("heizen", "warmwasser"))


async def _messe(mitschrift_ab: date | None) -> dict:
    import backend.services.kanal.schreiber as sch
    from backend.api.routes.energie_profil.tag import get_tag_detail

    echt_schreiben, echt_kurve = sch.schreibe_betriebsart_mitschrift_sicher, mx._kurve

    async def mitschrift(db, anlage, datum, modus_je_stunde):
        if mitschrift_ab is None or datum < mitschrift_ab:
            return 0
        return await echt_schreiben(db, anlage, datum, modus_je_stunde)

    form = am.MATRIX_FORMEN["M05"]
    verz = tempfile.mkdtemp(prefix="eedc-v1-")
    try:
        engine, db = await mx._neue_db(f"{verz}/ha.db")
        svc = am.seed_ha(form)
        try:
            aid, ids = await am.seed_anlage(db, form)

            def kurve(pvform):
                k = echt_kurve(pvform)
                key = f"waermepumpe_{ids['WP']}"
                k["serien"] = [*k["serien"], {"key": key, "kategorie": "waermepumpe", "seite": "senke",
                                              "bidirektional": False}]
                for p in (*k["punkte"], *k["vortagsrand"]):
                    p["werte"] = {**p["werte"], key: -0.3}
                return k

            with am.umgebung(form, svc):
                await mx.fuelle_spiegel(engine, aid, svc)
                with patch.object(sch, "schreibe_betriebsart_mitschrift_sicher", mitschrift), \
                        patch.object(mx, "_kurve", kurve):
                    await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                await mx.baue_abgeleitete_nach_tagen(engine, aid)
                out = {"tage": [_split(am._flach(await get_tag_detail(anlage_id=aid, datum=t, db=db))) for t in TAGE]}
                for monat in (6, 7):
                    out[f"cockpit_{monat}"] = _split(await am.miss_cockpit_monat(db, aid, ids, monat))
                    f = await am.miss_fakten(db, aid, ids, monat, tageswerte=True)
                    out[f"fakten_{monat}"] = _split(f["wp"], "modus_strom_")
                    out[f"jahr_{monat}"] = _split((await am.miss_jahr(db, aid))["monate"][str(monat)])
                out["uebersicht"] = _split(await am.miss_uebersicht(db, aid))
                ha = (await am.miss_ha_export(db, aid, ids))["inv"]["WP"]
                out["ha_export"] = tuple(round(ha.get(f"wp_strom_{k}_modus_kwh") or 0.0, 2) for k in ("heizen", "warmwasser"))
            return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


def _summe(tage: list, monat: int) -> tuple:
    werte = [w for t, w in zip(TAGE, tage) if t.month == monat]
    return tuple(round(sum(w[i] for w in werte), 2) for i in (0, 1))


def _monatssichten_gleich(m: dict) -> None:
    for monat, soll in ((6, (198.0, 18.0)), (7, (19.8, 1.8))):
        for sicht in ("cockpit", "fakten", "jahr"):
            assert m[f"{sicht}_{monat}"] == soll, (sicht, monat, m[f"{sicht}_{monat}"])
    assert m["uebersicht"] == (217.8, 19.8)
    assert m["ha_export"] == (217.8, 19.8)


async def test_ohne_mitschrift_traegt_der_monat_die_aufteilung_der_tage():
    """Juni 30 × 6,6 / 0,6 = 198/18, Juli 3 × = 19,8/1,8 in Cockpit → Monat, Monats-Fakten und Jahr; Übersicht und HA-Export
    217,8/19,8 — jede Sicht dieselbe Zahl, und sie ist die Σ der Tage (Cockpit → Tag). Bis zum Bau waren alle Monatssichten
    leer bzw. 0."""
    m = await _messe(None)
    assert all(w == (6.6, 0.6) for w in m["tage"]), m["tage"]
    assert (_summe(m["tage"], 6), _summe(m["tage"], 7)) == ((198.0, 18.0), (19.8, 1.8))
    _monatssichten_gleich(m)


async def test_vor_dem_beginn_der_mitschrift_unveraendert():
    """Gegenprobe: Mitschrift ab 02.07. — der abgeleitete Kanal deckt Juni und Juli nicht, die WP-Gruppe wählt ``bestand``
    (Split der Stundenzeilen, wie vor dem Bau). Die Monatssichten nennen dieselben Zahlen."""
    _monatssichten_gleich(await _messe(date(2026, 7, 2)))
